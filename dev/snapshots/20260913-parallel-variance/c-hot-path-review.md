# C热路径只读审查与未应用的最小草案

本页仅审查现有候选，没有修改产品源码、编译或运行构建负载。[draft.patch](draft.patch)只是待决定的草案。其基准hnswbuild.c SHA为`f7564f02a18c481ad5050e9e0d7e09597652fbce7ce30e3c88d582c753e470ee`；当前诊断镜像继续使用旧候选。

## 一个确定冗余，但尚未证明有可测收益的读取

`BuildCallback`在并行leader参与扫描时，因`reportBuildPhase=true`，每row调用`ReportBuildPhase`。该函数读取共享`graph->buildPhase`，随后才与leader私有`reportedBuildPhase`比较。当前实现的图阶段只按2（LOAD_MEMORY）→3（FLUSH）→4（LOAD_DISK）前进；到达4后，剩余tuple回调不可能再看到新图阶段。因此，在本地已发布4之后的后续回调里，这一读取可以确定省去。

草案只给`BuildCallback`的条件增加“本地尚未报告LOAD_DISK”，没有新增共享字段、改变布局或修改`ReportBuildPhase`自身。代价是一个leader私有字段比较；好处是终态时省去函数体中的读取和判断，不预设净收益。

**准确量级：**只省去leader本人在发布磁盘阶段之后处理的剩余row，每row至多一次共享读取。并行30,000行、2 worker加leader、立即spill的已有日志中，leader大约处理10,000行，因此可省去约10,000次读取，而不是全体30,000次。中途spill节省更少；两项未证明的并行无spill用例几乎没有任何读取可省，因为整个扫描期间都保持LOAD_MEMORY。不能拿这个草案声称同时解决三项验收，更不能预设解释5%以上波动。

**读的性质：**本地OpenTenBase `src/include/port/atomics.h:229–242`明确写明`pg_atomic_read_u32`没有barrier语义；`port/atomics/generic.h:46–49`回退实现只是读取volatile value。不应未经实际编译/反汇编称它是acquire读或一次RMW。即便共享phase值稳定，附近字段可能活跃；反之，如果本来就需读取同一缓存行，额外开销可能很小。没有可测收益时，不应为了改动而破坏旧候选证据。

## 语义证明与回归边界

- **尚未发布磁盘阶段时不减频。**本地值初始为0，内存为2、flush为3，均继续每row观察；worker发起flush时，leader在阻塞于flushLock之前仍有机会对外发布FLUSH。不能将轮询移到`InsertTuple`之后而声称完全等价，因为那会失去等待flush期间的及时报告。
- **只跳过已经发布过的终态。**CAS推进保持单调，当前所有`AdvanceBuildPhase`目标仅为3和4；本地4不会对应后续更早的图阶段。条件位于NULL检查前，NULL/非法向量的现有处理顺序不变。
- **直接调用完全不变。**`BuildGraph`开始时、`ParallelHeapScan`等待循环及`AdvanceBuildPhase`内部的`ReportBuildPhase`调用不受草案影响。若leader最后一个tuple之后才发生worker阶段切换，等待循环仍会读取并发布最新阶段。
- **WAL完全不变。**`BuildIndex`在扫描和图处理结束后直接调用`pgstat_progress_update_param(..., PROGRESS_HNSW_PHASE_WAL)`，并不通过本地缓存或共享graph阶段；跳过tuple回调的重复磁盘报告不会屏蔽WAL。
- **serial与worker分支不变。**serial路径的`reportBuildPhase`原本为false，阶段由直接Advance/Report调用发布；并行worker的`progress=false`也不走这段回调轮询。
- **没有删去同步。**这次atomic读只用于进度显示，没有barrier语义；图访问仍受原flushLock、allocatorLock和完成等待约束。全部这些操作都没有变化。
- **适用范围要写清。**未来若在tuple扫描过程中新增LOAD_DISK之后的图阶段，需要重新检查这个终态假设；当前WAL并非这种情况。

若以后应用草案，至少复验并行立即spill/中途spill、leader自己触发及worker触发flush、leader提前完成扫描、无spill、serial、取消/失败路径，以及专项进度/计时TAP。保留旧候选，先用相同构建条件作有界原候选／草案对照。不能用“读取少了”替代性能证据。

## 布局：目前能说什么

候选的`buildPhase`和`timing`追加在`HnswGraph`的`flushed`之后，原`lock`、`indtuples`、各LWLock及内存字段的声明顺序没有插入变化。`HnswShared.graphData`之前也没有新字段。需要区分三件事：相对字段偏移、结构体总大小导致后续parallel scan descriptor偏移、DSM实际基址对缓存行的余数。

源码里`ALIGNOF_BUFFER=32`，`PG_CACHE_LINE_SIZE=128`；后者是项目使用的保守常量，不等于已经实测本机物理一致性单元。`shm_toc_allocate`从区域尾部按BUFFERALIGN分配，不保证128字节对齐。仅看offsetof无法断言某两字段在实际运行中一定共线，也不能只看“新字段追加在末尾”就说所有地址完全没变。

`buildPhase`临近`flushLock`和`flushed`。`InsertTuple`每个有效tuple都对flushLock执行shared acquire/release，稳定磁盘阶段也一样，所以“phase值不再写”不代表其所在缓存行没有其他写入。另一方面，此锁原本就必须访问；新增读究竟引入多少额外流量，要看实际布局/地址和对照，不能直接归因。

下列辅助器可由主任务在既有隔离编译环境，分别使用**原版与候选的实际PG18头文件/编译配置**编译运行。此页没有执行它。它输出静态尺寸、相对偏移以及32字节对齐基址在64/128字节线假设下的共线可能性；不会把可能性当成实际DSM地址证据。

```c
#include "postgres.h"
#include "portability/instr_time.h"
#include "access/relscan.h"
#include "src/hnsw.h"
#include <stddef.h>
#include <stdio.h>
#undef printf

#define FIELD(T, F) printf(#T "." #F " offset=%zu size=%zu\n", \
                            offsetof(T, F), sizeof(((T *) 0)->F))
int main(void)
{
    size_t line, base;
    printf("PG_VERSION_NUM=%d ALIGNOF_BUFFER=%d PG_CACHE_LINE_SIZE=%d\n",
           PG_VERSION_NUM, ALIGNOF_BUFFER, PG_CACHE_LINE_SIZE);
    printf("slock=%zu LWLock=%zu CV=%zu instr_time=%zu graph=%zu shared=%zu scan=%zu blockscan=%zu\n",
           sizeof(slock_t), sizeof(LWLock), sizeof(ConditionVariable), sizeof(instr_time),
           sizeof(HnswGraph), sizeof(HnswShared), sizeof(ParallelTableScanDescData),
           sizeof(ParallelBlockTableScanDescData));
    FIELD(HnswGraph, lock); FIELD(HnswGraph, head); FIELD(HnswGraph, indtuples);
    FIELD(HnswGraph, entryLock); FIELD(HnswGraph, entryWaitLock);
    FIELD(HnswGraph, allocatorLock); FIELD(HnswGraph, memoryUsed);
    FIELD(HnswGraph, memoryTotal); FIELD(HnswGraph, flushLock); FIELD(HnswGraph, flushed);
    FIELD(HnswShared, workersdonecv); FIELD(HnswShared, mutex);
    FIELD(HnswShared, nparticipantsdone); FIELD(HnswShared, reltuples);
    FIELD(HnswShared, graphData);
    FIELD(ParallelBlockTableScanDescData, phs_mutex);
    FIELD(ParallelBlockTableScanDescData, phs_nallocated);
    printf("parallel_scan_offset=%zu nallocated_from_shared=%zu\n",
           (size_t) BUFFERALIGN(sizeof(HnswShared)),
           (size_t) BUFFERALIGN(sizeof(HnswShared)) +
           offsetof(ParallelBlockTableScanDescData, phs_nallocated));
#ifdef PROGRESS_HNSW_PHASE_LOAD_DISK
    FIELD(HnswGraph, buildPhase); FIELD(HnswGraph, timing);
    FIELD(HnswGraphTiming, enabled); FIELD(HnswGraphTiming, spillRequested);
    FIELD(HnswGraphTiming, flushStarted); FIELD(HnswGraphTiming, flushFinished);
    for (line = 64; line <= 128; line *= 2)
        for (base = 0; base < line; base += ALIGNOF_BUFFER)
        {
            size_t graph = base + offsetof(HnswShared, graphData);
            size_t phase = graph + offsetof(HnswGraph, buildPhase);
            printf("line=%zu assumed_shared_base_mod_line=%zu phase_with_graph_lock=%d phase_with_indtuples=%d phase_with_flushLock=%d\n",
                   line, base,
                   phase / line == (graph + offsetof(HnswGraph, lock)) / line,
                   phase / line == (graph + offsetof(HnswGraph, indtuples)) / line,
                   phase / line == (graph + offsetof(HnswGraph, flushLock)) / line);
        }
#else
    (void) line; (void) base;
#endif
    return 0;
}
```

例：在隔离的对应源码根目录，以该镜像的`/opt/opentenbase/bin/pg_config --includedir-server`为server include目录、当前源码根目录为另一个include目录，使用同一GCC编译上述独立程序；`-std=gnu11 -O2`足够，不需要链接数据库或启动实例。启用LOCK_DEBUG等改变结构体的配置时，输出必须单列，不能与当前构建混用。

## 后续实测布局（主任务执行，未应用草案）

在75次数据库构建结束后，主任务用锁定的编译器镜像编译运行上述辅助器；
输入是两份隔离插桩源码的头文件，生成器测试已验证其共享结构声明与未插桩输入相同。
未启动数据库负载。第一次编译成功但临时文件系统默认不可执行，退出126并保留
`layout-manifest.json`及日志；第二次明确为自有临时文件系统启用exec后成功，两个
短命容器均自动清理。见[编译身份](layout-manifest-02.json)及[原始输出](layout-build-02.stdout.txt)。

- 实际PG版本180006，buffer对齐32字节，项目cache line常量128字节。
- 原版/候选HnswGraph为120/152字节，HnswShared为160/192字节；原有字段偏移相同。
- graphData在shared偏移40；graph内flushLock偏移96，新增buildPhase偏移116，timing偏移120。
- 后续扫描描述符由shared偏移160变192；phs_nallocated从shared偏移200变232。
- 在64/128字节线及所有32字节对齐的shared基址余数假设下，phase与flushLock共线。
  对128字节线且shared基址余数96的假设，phase也可能与graph.lock/indtuples共线。

这些是实际编译尺寸与条件化的地址计算，未采集运行中DSM实际基址、缓存失效或
一致性通信。它们不能证明缓存竞争回归，也不等于每个图节点增加32字节。草案仍未应用。
