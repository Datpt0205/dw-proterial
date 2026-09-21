-- ---------------------------------------------------------------------------
-- Partition maintenance after `platform.model_usage_ledger` was removed.
--
-- `ensure_time_partitions` names its parents in an array. Left alone it would
-- try to create a partition OF a table that no longer exists, every hour, for
-- ever — so the array shrinks to the one table that is still partitioned.
--
-- Two things are taken away while the file is open, because both were facts
-- about a second table that is gone:
--
-- * `_ensure_one_partition` chose the timestamp column with
--   `CASE parent WHEN 'audit_events' THEN 'occurred_at' ELSE 'created_at' END`.
--   With one parent the ELSE is unreachable, and the mapping was a second copy
--   of something the table already declares. It now reads the partition key
--   from the catalog, so there is nothing left to drift.
-- * `drop_expired_partitions` took a cutoff per table. One table, one cutoff.
--   The old two-argument version is dropped rather than left as an overload
--   nothing calls.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION platform._ensure_one_partition(parent text, month date)
RETURNS text
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    part text := parent || '_' || to_char(month, 'YYYY_MM');
    fallback text := parent || '_default';
    stamp text;
    next_month date := (month + interval '1 month')::date;
    predicate constant text :=
        'tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid';
    stranded boolean;
BEGIN
    IF to_regclass('platform.' || quote_ident(part)) IS NOT NULL THEN
        RETURN NULL;
    END IF;
    -- The partition key, from the table that declares it. A mapping written
    -- here would be a second source of truth for something the schema already
    -- answers, and it would be wrong the first time a table is partitioned on a
    -- differently named column.
    SELECT a.attname INTO stamp
    FROM pg_partitioned_table p
    JOIN pg_attribute a ON a.attrelid = p.partrelid AND a.attnum = p.partattrs[0]
    WHERE p.partrelid = ('platform.' || quote_ident(parent))::regclass;
    IF stamp IS NULL THEN
        RAISE EXCEPTION 'platform.% is not range-partitioned', parent;
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
    FOREACH parent IN ARRAY ARRAY['audit_events'] LOOP
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

DROP FUNCTION IF EXISTS platform.drop_expired_partitions(timestamptz, timestamptz);

CREATE OR REPLACE FUNCTION platform.drop_expired_partitions(audit_cutoff timestamptz)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    found record;
    range_end timestamptz;
BEGIN
    -- A NULL cutoff means never dropped, which is what the policy file ships
    -- with: DROP PARTITION is instant and irreversible, so the term has to be a
    -- number somebody wrote.
    IF audit_cutoff IS NULL THEN
        RETURN;
    END IF;
    FOR found IN
        SELECT child.relname AS part
        FROM pg_inherits i
        JOIN pg_class parent ON parent.oid = i.inhparent
        JOIN pg_class child ON child.oid = i.inhrelid
        JOIN pg_namespace n ON n.oid = parent.relnamespace
        WHERE n.nspname = 'platform' AND parent.relname = 'audit_events'
        ORDER BY child.relname
    LOOP
        -- Only the names this file's own creation function makes. The DEFAULT
        -- partition and anything a person added by hand fall through — a sweep
        -- that guessed at an unfamiliar partition's range would be guessing
        -- about which rows to destroy.
        CONTINUE WHEN found.part !~ '^audit_events_\d{4}_\d{2}$';
        range_end := to_date(right(found.part, 7), 'YYYY_MM') + interval '1 month';
        IF range_end <= audit_cutoff THEN
            EXECUTE format('DROP TABLE platform.%I', found.part);
            RETURN NEXT found.part;
        END IF;
    END LOOP;
END;
$fn$;

REVOKE EXECUTE ON FUNCTION platform.drop_expired_partitions(timestamptz) FROM PUBLIC;

DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
        GRANT EXECUTE ON FUNCTION platform.drop_expired_partitions(timestamptz) TO dw_app;
    END IF;
END
$grant$;
