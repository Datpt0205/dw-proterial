-- ---------------------------------------------------------------------------
-- Partition maintenance for the two time-series tables, and two holes the
-- DEFAULT partition was hiding.
--
-- The baseline created `platform.audit_events` and `platform.model_usage_ledger`
-- as range-partitioned and said, in a comment, that "an operational job creates
-- real monthly partitions ahead of time". That job was never written. What
-- existed instead was a single DEFAULT partition per table holding every row
-- ever written, which means the retention story for audit — DROP PARTITION,
-- instant, nothing left to vacuum — could not execute at all.
--
-- Three things are wrong today and each is fixed below.
--
-- 1. THE ROWS ARE ALL IN THE DEFAULT. A default partition cannot be dropped,
--    and while it holds rows for a month, that month's partition cannot even be
--    created — Postgres scans the default and refuses. So the rows are relocated
--    into real monthly partitions, and the relocation lives in the creating
--    function rather than only in this migration: a row written between two
--    maintenance passes lands in the default again, and a job that could not
--    recover from that would be one missed window from stuck for ever.
--
-- 2. A NEW PARTITION DOES NOT INHERIT RLS. Migration 0009 found this the hard
--    way: a partition addressed by its own name uses its own settings, and the
--    two defaults were readable across tenants. Anything that creates a
--    partition must enable, force and police it in the same breath, or it
--    re-opens that hole every month. That is why creation lives in a function
--    and not in a runbook.
--
-- 3. THE AUDIT LOG IS NOT APPEND-ONLY. `0001_platform_grants.sql` says so in
--    as many words — "enforced by the grant rather than by convention" — and
--    revokes UPDATE and DELETE on `platform.audit_events`. It never revoked them
--    on `platform.audit_events_default`, which had already taken SELECT, INSERT,
--    UPDATE, DELETE from the blanket grant one statement earlier. Measured, not
--    inferred: as `dw_app`, with only `app.tenant_id` set, both
--      DELETE FROM platform.audit_events_default WHERE ctid = (...)
--      UPDATE platform.audit_events_default SET action = 'rewritten' WHERE ...
--    succeeded. `ALTER DEFAULT PRIVILEGES` means every future partition would
--    have arrived the same way, so the revoke belongs in the creating function
--    too, not only in this one-off repair.
--
-- WHY A FUNCTION AND NOT A WORKER QUERY. Creating a partition is DDL on a table
-- `dw_app` does not own, and `dw_app` deliberately lacks BYPASSRLS. A SECURITY
-- DEFINER function owned by `dw_migrator` is the standard answer and is what
-- keeps the maintenance lane inside the worker instead of in a cron job someone
-- has to remember to install. It is written to be a narrow one: `search_path` is
-- fixed, EXECUTE is revoked from PUBLIC, and NO caller-supplied string ever
-- names a table — the two parents are a constant in the body, and the only
-- arguments are a bounded integer and two timestamps.
-- ---------------------------------------------------------------------------

-- One partition, created the only way a partition may be created here.
-- Not SECURITY DEFINER and not granted to anybody: it takes a table name, so
-- only the definer functions below may reach it.
--
-- It also RELOCATES whatever the default partition is already holding for that
-- month, which is what makes falling behind recoverable rather than terminal.
CREATE OR REPLACE FUNCTION platform._ensure_one_partition(parent text, month date)
RETURNS text
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    part text := parent || '_' || to_char(month, 'YYYY_MM');
    fallback text := parent || '_default';
    stamp text := CASE parent WHEN 'audit_events' THEN 'occurred_at' ELSE 'created_at' END;
    next_month date := (month + interval '1 month')::date;
    predicate constant text :=
        'tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid';
    stranded boolean;
BEGIN
    IF to_regclass('platform.' || quote_ident(part)) IS NOT NULL THEN
        RETURN NULL;
    END IF;
    -- Asked before the expensive path is taken: detaching the default takes an
    -- ACCESS EXCLUSIVE lock, and this runs hourly on a table that is almost
    -- always already in order.
    EXECUTE format(
        'SELECT EXISTS (SELECT 1 FROM platform.%I WHERE %I >= %L AND %I < %L)',
        fallback, stamp, month, stamp, next_month
    ) INTO stranded;
    IF stranded THEN
        EXECUTE format(
            'ALTER TABLE platform.%I DETACH PARTITION platform.%I', parent, fallback
        );
    END IF;

    EXECUTE format(
        'CREATE TABLE platform.%I PARTITION OF platform.%I FOR VALUES FROM (%L) TO (%L)',
        part, parent, month, next_month
    );
    -- Postgres does not inherit row security to a partition created later, and
    -- a partition addressed by name uses its own settings. FORCE as well:
    -- without it the owner reads straight past the policy, and the owner is
    -- exactly who runs this.
    EXECUTE format('ALTER TABLE platform.%I ENABLE ROW LEVEL SECURITY', part);
    EXECUTE format('ALTER TABLE platform.%I FORCE ROW LEVEL SECURITY', part);
    EXECUTE format(
        'CREATE POLICY %I ON platform.%I USING (%s) WITH CHECK (%s)',
        'tenant_isolation_' || part, part, predicate, predicate
    );
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
        -- `ALTER DEFAULT PRIVILEGES` has already handed this partition SELECT,
        -- INSERT, UPDATE and DELETE. For the audit log the last two are exactly
        -- what the application must not have.
        IF parent = 'audit_events' THEN
            EXECUTE format('REVOKE UPDATE, DELETE ON platform.%I FROM dw_app', part);
        END IF;
    END IF;

    IF stranded THEN
        -- Back in through the PARENT, so the rows route themselves into the
        -- partition just made. Only this month's: the default may legitimately
        -- be holding other months that nothing has asked for yet.
        EXECUTE format(
            'INSERT INTO platform.%I SELECT * FROM platform.%I WHERE %I >= %L AND %I < %L',
            parent, fallback, stamp, month, stamp, next_month
        );
        EXECUTE format(
            'DELETE FROM platform.%I WHERE %I >= %L AND %I < %L',
            fallback, stamp, month, stamp, next_month
        );
        EXECUTE format(
            'ALTER TABLE platform.%I ATTACH PARTITION platform.%I DEFAULT', parent, fallback
        );
    END IF;
    RETURN part;
END;
$fn$;

-- Create this month and the next `months_ahead` for both tables.
-- Returns the partitions it actually made, so a caller can log a number rather
-- than assume the call did something.
CREATE OR REPLACE FUNCTION platform.ensure_time_partitions(months_ahead integer)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    parent text;
    step integer;
    made text;
    first_month constant date := date_trunc('month', now())::date;
BEGIN
    -- Bounded rather than trusted: the argument crosses a privilege boundary,
    -- and 24 months of empty partitions is the most any schedule needs.
    IF months_ahead IS NULL OR months_ahead < 1 OR months_ahead > 24 THEN
        RAISE EXCEPTION 'months_ahead must be between 1 and 24, got %', months_ahead;
    END IF;
    FOREACH parent IN ARRAY ARRAY['audit_events', 'model_usage_ledger'] LOOP
        FOR step IN 0..months_ahead LOOP
            made := platform._ensure_one_partition(
                parent, (first_month + (step || ' month')::interval)::date
            );
            IF made IS NOT NULL THEN
                RETURN NEXT made;
            END IF;
        END LOOP;
    END LOOP;
END;
$fn$;

-- Drop partitions whose whole range is older than the cutoff for their table.
-- A NULL cutoff means that table is never dropped, which is the default the
-- policy file ships with: DROP PARTITION is instant and irreversible, so the
-- term has to be a number somebody wrote.
CREATE OR REPLACE FUNCTION platform.drop_expired_partitions(
    audit_cutoff timestamptz, usage_cutoff timestamptz
)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    found record;
    cutoff timestamptz;
    range_end timestamptz;
BEGIN
    FOR found IN
        SELECT parent.relname AS parent, child.relname AS part
        FROM pg_inherits i
        JOIN pg_class parent ON parent.oid = i.inhparent
        JOIN pg_class child ON child.oid = i.inhrelid
        JOIN pg_namespace n ON n.oid = parent.relnamespace
        WHERE n.nspname = 'platform'
          AND parent.relname IN ('audit_events', 'model_usage_ledger')
        ORDER BY child.relname
    LOOP
        cutoff := CASE found.parent
            WHEN 'audit_events' THEN audit_cutoff
            ELSE usage_cutoff
        END;
        CONTINUE WHEN cutoff IS NULL;
        -- Only the names this file's own creation function makes. The DEFAULT
        -- partition and anything a person added by hand fall through — a sweep
        -- that guessed at an unfamiliar partition's range would be guessing
        -- about which rows to destroy.
        CONTINUE WHEN found.part !~ ('^' || found.parent || '_\d{4}_\d{2}$');
        range_end := to_date(right(found.part, 7), 'YYYY_MM') + interval '1 month';
        IF range_end <= cutoff THEN
            EXECUTE format('DROP TABLE platform.%I', found.part);
            RETURN NEXT found.part;
        END IF;
    END LOOP;
END;
$fn$;

-- A function is EXECUTE-to-PUBLIC by default, which for a SECURITY DEFINER one
-- would mean every role in the database can run DDL as `dw_migrator`.
REVOKE EXECUTE ON FUNCTION platform._ensure_one_partition(text, date) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION platform.ensure_time_partitions(integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION platform.drop_expired_partitions(timestamptz, timestamptz)
    FROM PUBLIC;

-- ---- the one-off repair --------------------------------------------------
DO $repair$
DECLARE
    parent text;
    stamp text;
    month date;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
        GRANT EXECUTE ON FUNCTION platform.ensure_time_partitions(integer) TO dw_app;
        GRANT EXECUTE ON FUNCTION platform.drop_expired_partitions(timestamptz, timestamptz)
            TO dw_app;
        -- What `0001_platform_grants.sql` meant to say, on the partition it
        -- forgot. Proven necessary against a running database, not inferred.
        REVOKE UPDATE, DELETE ON platform.audit_events_default FROM dw_app;
    END IF;

    FOREACH parent IN ARRAY ARRAY['audit_events', 'model_usage_ledger'] LOOP
        stamp := CASE parent WHEN 'audit_events' THEN 'occurred_at' ELSE 'created_at' END;
        -- Every month the default is already holding. `_ensure_one_partition`
        -- owns the relocation, so this loop only has to say which months.
        FOR month IN EXECUTE format(
            'SELECT DISTINCT date_trunc(''month'', %I)::date FROM platform.%I ORDER BY 1',
            stamp, parent || '_default'
        ) LOOP
            PERFORM platform._ensure_one_partition(parent, month);
        END LOOP;
    END LOOP;
END
$repair$;
