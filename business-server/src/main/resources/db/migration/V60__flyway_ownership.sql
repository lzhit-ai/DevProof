CREATE TABLE public.schema_migration_ownership (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    owner text NOT NULL CHECK (owner='FLYWAY'),
    baseline_revision text NOT NULL,
    baseline_catalog_hash text NOT NULL,
    handed_over_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO public.schema_migration_ownership(id,owner,baseline_revision,baseline_catalog_hash)
VALUES (true,'FLYWAY','059_java_security_profiles','sha256:556b8d4c82db27f22384b5b2deb57d7494b33ca6e4af2d29cfa34e2adbd2d0ea');
