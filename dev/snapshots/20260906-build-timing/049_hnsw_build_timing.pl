use strict;
use warnings FATAL => 'all';
use PostgreSQL::Test::Cluster;
use PostgreSQL::Test::Utils;
use JSON::PP qw(decode_json);
use Test::More;

my $node = PostgreSQL::Test::Cluster->new('timing');
$node->init;
$node->append_conf('postgresql.conf', qq(
max_parallel_workers = 4
max_worker_processes = 8
wal_level = replica
));
$node->start;
$node->safe_psql('postgres', q(
CREATE EXTENSION vector;
CREATE TABLE tst (id int, v vector(8));
SELECT setseed(0.42);
INSERT INTO tst SELECT i, ARRAY[random(),random(),random(),random(),
 random(),random(),random(),random()] FROM generate_series(1,5000) i;
ANALYZE tst;
));

sub summaries
{
	my ($stderr) = @_;
	return map { decode_json($_) } $stderr =~ /hnsw build timing: (\{[^\n]+\})/g;
}

sub check_timeline
{
	my ($record, $spill, $workers, $wal, $label) = @_;
	is($record->{version}, 1, "$label: schema version");
	is($record->{status}, 'complete', "$label: complete AM call");
	is($record->{scope}, 'hnsw_build', "$label: internal scope");
	is($record->{clock}, 'elapsed_wall', "$label: wall time, not worker sum");
	is(!!$record->{spill}, !!$spill, "$label: spill applicability");
	is($record->{parallel_workers}, $workers, "$label: actual launched workers");
	my @names = qw(setup memory_build spill_drain flush disk_insert finalize wal cleanup);
	is_deeply([map { $_->{phase} } @{$record->{phases}}], \@names,
		"$label: exactly one of each phase, in order");
	my $last = 0;
	for my $phase (@{$record->{phases}})
	{
		my $name = $phase->{phase};
		my $na = (!$spill && ($name eq 'spill_drain' || $name eq 'disk_insert'))
			|| (!$wal && $name eq 'wal');
		if ($na)
		{
			ok(!defined($phase->{start_us}) && !defined($phase->{end_us}), "$label: $name is N/A");
			next;
		}
		is($phase->{start_us}, $last, "$label: $name has no gap or overlap");
		cmp_ok($phase->{end_us}, '>=', $phase->{start_us}, "$label: $name monotonic");
		$last = $phase->{end_us};
	}
	is($last, $record->{total_us}, "$label: phases cover total exactly");
	cmp_ok($last, '>', 0, "$label: positive elapsed time");
}

my ($ret, $stdout, $stderr) = $node->psql('postgres', q(
SET max_parallel_maintenance_workers = 0;
CREATE INDEX default_idx ON tst USING hnsw (v vector_l2_ops);
));
is($ret, 0, 'default build succeeds');
unlike($stderr, qr/hnsw build timing:/, 'timing defaults to off');

for my $workers (0, 2)
{
	for my $spill (0, 1)
	{
		my $memory = $spill ? ($workers ? '4MB' : '1MB') : '64MB';
		my $label = "workers=$workers spill=$spill";
		($ret, $stdout, $stderr) = $node->psql('postgres', qq(
SET client_min_messages = NOTICE;
SET hnsw.build_timing = on;
SET maintenance_work_mem = '$memory';
SET max_parallel_maintenance_workers = $workers;
SET min_parallel_table_scan_size = 0;
ALTER TABLE tst SET (parallel_workers = $workers);
CREATE INDEX timing_${workers}_${spill} ON tst USING hnsw (v vector_l2_ops);
));
		is($ret, 0, "$label: build succeeds") or diag($stderr);
		my @records = summaries($stderr);
		is(scalar @records, 1, "$label: leader emits exactly one summary");
		check_timeline($records[0], $spill, $workers, 1, $label) if @records == 1;
		if ($spill)
		{
			like($stderr, qr/graph no longer fits/, "$label: actual spill NOTICE");
		}
	}
}

# Unlogged main and init forks are different AM invocations. Main skips WAL.
($ret, $stdout, $stderr) = $node->psql('postgres', q(
SET hnsw.build_timing = on;
CREATE UNLOGGED TABLE empty_tst (v vector(8));
CREATE INDEX unlogged_idx ON empty_tst USING hnsw (v vector_l2_ops);
));
is($ret, 0, 'empty unlogged index succeeds');
my @forks = summaries($stderr);
is_deeply([map { $_->{fork} } @forks], [0, 3], 'main and init fork summaries are distinct');
for my $record (@forks)
{
	check_timeline($record, 0, 0, $record->{fork} == 3, "fork=$record->{fork}");
}

# Slow expression lets the test cancel an actual build, without polling a
# fleeting build phase. The same backend must then build successfully.
$node->safe_psql('postgres', q(
CREATE FUNCTION slow_vector(v vector) RETURNS vector
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN PERFORM pg_sleep(0.01); RETURN v; END $$;
CREATE FUNCTION failing_vector(v vector) RETURNS vector
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN RAISE EXCEPTION 'timing test failure'; END $$;
));
for my $workers (0, 2)
{
	my $session = $node->background_psql('postgres', on_error_stop => 0);
	$session->query_safe(qq(
SET hnsw.build_timing = on;
SET client_min_messages = NOTICE;
SET max_parallel_maintenance_workers = $workers;
SET min_parallel_table_scan_size = 0;
ALTER TABLE tst SET (parallel_workers = $workers);
));
	my $pid = $session->query_safe('SELECT pg_backend_pid()');
	$session->query_until(qr/starting/, qq(\n\\echo starting
CREATE INDEX cancelled_$workers ON tst USING hnsw ((slow_vector(v)::vector(8)) vector_l2_ops);
));
	ok($node->poll_query_until('postgres',
		"SELECT wait_event = 'PgSleep' FROM pg_stat_activity WHERE pid = $pid"),
		"workers=$workers: entered slow build expression");
	is($node->safe_psql('postgres', "SELECT pg_cancel_backend($pid)"), 't', 'cancel accepted');
	$session->query('SELECT 1');
	like($session->{stderr}, qr/canceling statement due to user request/, 'build cancelled');
	unlike($session->{stderr}, qr/hnsw build timing:/, 'cancelled build emits no complete summary');
	$session->{stderr} = '';
	$session->query(qq(CREATE INDEX failed_$workers ON tst USING hnsw ((failing_vector(v)::vector(8)) vector_l2_ops)));
	like($session->{stderr}, qr/timing test failure/, 'expression error exercised');
	unlike($session->{stderr}, qr/hnsw build timing:/, 'failed build emits no complete summary');
	$session->{stderr} = '';
	$session->query(qq(CREATE INDEX recovered_$workers ON tst USING hnsw (v vector_l2_ops)));
	my @recovered = summaries($session->{stderr});
	is(scalar @recovered, 1, 'same backend recovers with a fresh single summary');
	check_timeline($recovered[0], 0, $workers, 1, "recovered=$workers") if @recovered == 1;
	$session->{stderr} = '';
	$session->query(qq(REINDEX INDEX recovered_$workers));
	my @repeated = summaries($session->{stderr});
	is(scalar @repeated, 1, 'repeated build has exactly one fresh summary');
	$session->{stderr} = '';
	$session->query_safe('SET hnsw.build_timing = off');
	$session->query(qq(REINDEX INDEX recovered_$workers));
	unlike($session->{stderr}, qr/hnsw build timing:/, 'turning off suppresses summary');
	$session->{stderr} = '';
	is($session->query_safe("SELECT count(*) FROM pg_stat_progress_create_index WHERE pid = $pid"), 0,
		'no stale build progress after recovery');
	$session->quit;
}

$node->stop;
done_testing();
