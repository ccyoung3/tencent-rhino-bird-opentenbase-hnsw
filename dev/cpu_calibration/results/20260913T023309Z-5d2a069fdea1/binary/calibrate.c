#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* Exploratory fixed work, deliberately no database, graph, RNG or graph locks. */
#define DIMENSIONS 32
#define INPUTS 1024
#define PARTICIPANTS 3
static float left[INPUTS][DIMENSIONS], right[INPUTS][DIMENSIONS];

/* noipa also prevents pure/const inference, specialization and loop hoisting.
 * The inner arithmetic loop remains available for ordinary vectorization. */
__attribute__((noinline, noipa)) static float
distance32(const float *a, const float *b)
{
    float result = 0;
    for (int j = 0; j < DIMENSIONS; ++j) {
        float difference = a[j] - b[j];
        result += difference * difference;
    }
    return result;
}

static void fail(const char *operation)
{
    perror(operation);
    exit(1);
}

static uint64_t wall_ns(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) fail("clock_gettime");
    return (uint64_t) value.tv_sec * UINT64_C(1000000000) + value.tv_nsec;
}

static int64_t timeval_us(struct timeval value)
{
    return (int64_t) value.tv_sec * INT64_C(1000000) + value.tv_usec;
}

static void transfer(int descriptor, void *buffer, size_t bytes, int writing)
{
    size_t completed = 0;
    while (completed != bytes) {
        ssize_t count = writing ? write(descriptor, (char *) buffer + completed, bytes - completed)
                                : read(descriptor, (char *) buffer + completed, bytes - completed);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) fail(writing ? "write" : "read");
        completed += (size_t) count;
    }
}

typedef struct Result {
    pid_t pid;
    uint64_t iterations, checksum, elapsed_ns;
    int64_t user_cpu_us, system_cpu_us, minor_faults, major_faults;
    int64_t voluntary_switches, involuntary_switches;
} Result;

static Result calculate(uint64_t iterations)
{
    Result result = {0};
    struct rusage before, after;
    uint64_t checksum = 0, completed = 0;
    uint64_t started = wall_ns();
    if (getrusage(RUSAGE_SELF, &before) != 0) fail("getrusage before");
    for (uint64_t i = 0; i < iterations; ++i) {
        unsigned int index = (unsigned int) ((i * UINT64_C(17)) & (INPUTS - 1));
        checksum += (uint64_t) distance32(left[index], right[index]);
        ++completed;
    }
    if (getrusage(RUSAGE_SELF, &after) != 0) fail("getrusage after");
    result.elapsed_ns = wall_ns() - started;
    result.pid = getpid();
    result.iterations = completed;
    result.checksum = checksum;
    result.user_cpu_us = timeval_us(after.ru_utime) - timeval_us(before.ru_utime);
    result.system_cpu_us = timeval_us(after.ru_stime) - timeval_us(before.ru_stime);
    result.minor_faults = after.ru_minflt - before.ru_minflt;
    result.major_faults = after.ru_majflt - before.ru_majflt;
    result.voluntary_switches = after.ru_nvcsw - before.ru_nvcsw;
    result.involuntary_switches = after.ru_nivcsw - before.ru_nivcsw;
    return result;
}

int main(int argc, char **argv)
{
    char *end;
    if (argc != 2) { fprintf(stderr, "usage: calibrate iterations\n"); return 2; }
    errno = 0;
    uint64_t iterations = strtoull(argv[1], &end, 10);
    if (errno || *end || iterations < 1 || iterations > UINT64_C(50000000)) return 2;
    uint64_t period_checksum = 0, remainder_checksum = 0;
    for (int i = 0; i < INPUTS; ++i)
        for (int j = 0; j < DIMENSIONS; ++j) {
            left[i][j] = (float) (((i * 11 + j * 7 + i / 13) % 17) - 8);
            right[i][j] = (float) (((i * 3 + j * 5 + i / 7) % 19) - 9);
        }
    /* Integer reference, outside all measured scopes. Every distance is exactly
     * representable in float; checksum fits uint64 and is independent of order. */
    for (uint64_t i = 0; i < INPUTS; ++i) {
        unsigned int index = (unsigned int) ((i * UINT64_C(17)) & (INPUTS - 1));
        uint64_t value = 0;
        for (int j = 0; j < DIMENSIONS; ++j) {
            int difference = (int) left[index][j] - (int) right[index][j];
            value += (uint64_t) (difference * difference);
        }
        period_checksum += value;
        if (i < iterations % INPUTS) remainder_checksum += value;
    }
    uint64_t expected_checksum = (iterations / INPUTS) * period_checksum + remainder_checksum;
    int start[2], output[2][2];
    if (pipe(start) != 0) fail("pipe start");
    for (int i = 0; i < 2; ++i) if (pipe(output[i]) != 0) fail("pipe output");
    pid_t children[2];
    for (int i = 0; i < 2; ++i) {
        children[i] = fork();
        if (children[i] < 0) fail("fork");
        if (children[i] == 0) {
            close(start[1]);
            close(output[i][0]);
            close(output[1 - i][0]); close(output[1 - i][1]);
            char ready = 'R';
            transfer(output[i][1], &ready, 1, 1);
            transfer(start[0], &ready, 1, 0);
            Result result = calculate(iterations);
            transfer(output[i][1], &result, sizeof(result), 1);
            close(output[i][1]); close(start[0]);
            _exit(0);
        }
    }
    close(start[0]);
    for (int i = 0; i < 2; ++i) {
        close(output[i][1]);
        char ready;
        transfer(output[i][0], &ready, 1, 0);
        if (ready != 'R') return 3;
    }
    uint64_t started = wall_ns();
    char release[2] = {'G', 'G'};
    transfer(start[1], release, sizeof(release), 1);
    close(start[1]);
    Result results[PARTICIPANTS];
    results[0] = calculate(iterations);
    for (int i = 0; i < 2; ++i) {
        transfer(output[i][0], &results[i + 1], sizeof(Result), 0);
        close(output[i][0]);
        int status;
        if (waitpid(children[i], &status, 0) < 0) fail("waitpid");
        if (!WIFEXITED(status) || WEXITSTATUS(status)) return 3;
    }
    uint64_t elapsed_ns = wall_ns() - started;
    cpu_set_t affinity;
    CPU_ZERO(&affinity);
    if (sched_getaffinity(0, sizeof(affinity), &affinity) != 0) fail("sched_getaffinity");
    printf("{\"schema\":1,\"test_only\":true,\"scope\":\"fixed_arithmetic_three_processes\","
           "\"dimensions\":32,\"inputs\":1024,\"expected_checksum\":%" PRIu64 ","
           "\"iterations_per_process\":%" PRIu64 ",\"elapsed_ns\":%" PRIu64 ",\"affinity\":[",
           expected_checksum, iterations, elapsed_ns);
    int separator = 0;
    for (int i = 0; i < CPU_SETSIZE; ++i) if (CPU_ISSET(i, &affinity)) {
        printf("%s%d", separator ? "," : "", i); separator = 1;
    }
    printf("],\"processes\":[");
    int valid = 1;
    for (int i = 0; i < PARTICIPANTS; ++i) {
        Result *r = &results[i];
        valid &= r->iterations == iterations && r->checksum == expected_checksum;
        printf("%s{\"role\":\"%s\",\"participant\":%d,\"pid\":%d,\"iterations\":%" PRIu64
               ",\"checksum\":%" PRIu64 ",\"elapsed_ns\":%" PRIu64
               ",\"user_cpu_us\":%" PRId64 ",\"system_cpu_us\":%" PRId64
               ",\"minor_faults\":%" PRId64 ",\"major_faults\":%" PRId64
               ",\"voluntary_switches\":%" PRId64 ",\"involuntary_switches\":%" PRId64 "}",
               i ? "," : "", i ? "worker" : "leader", i, (int) r->pid, r->iterations,
               r->checksum, r->elapsed_ns, r->user_cpu_us, r->system_cpu_us,
               r->minor_faults, r->major_faults, r->voluntary_switches, r->involuntary_switches);
    }
    printf("],\"verified\":%s}\n", valid ? "true" : "false");
    return valid ? 0 : 4;
}
