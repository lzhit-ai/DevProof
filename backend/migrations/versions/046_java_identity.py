"""Transfer registration ownership without rewriting existing users or password hashes."""

from alembic import op

revision = "046_java_identity"
down_revision = "045_verification_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("INSERT INTO business_write_owners(aggregate_key,owner) VALUES('identity','PYTHON')")
    op.execute("""CREATE FUNCTION devproof_guard_identity_writer() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE expected text; writer text;
        BEGIN
          SELECT owner INTO expected FROM business_write_owners WHERE aggregate_key='identity' FOR SHARE;
          writer:=coalesce(nullif(current_setting('devproof.business_writer',true),''),'PYTHON');
          IF expected IS DISTINCT FROM writer THEN RAISE EXCEPTION 'Identity aggregate is owned by another service'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$""")
    op.execute("CREATE TRIGGER users_identity_writer BEFORE INSERT OR UPDATE OR DELETE ON users FOR EACH ROW EXECUTE FUNCTION devproof_guard_identity_writer()")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM business_write_owners WHERE aggregate_key='identity' AND owner='JAVA') THEN
        RAISE EXCEPTION 'Hand identity ownership back before removing guards'; END IF; END $$""")
    op.execute("DROP TRIGGER users_identity_writer ON users")
    op.execute("DROP FUNCTION devproof_guard_identity_writer()")
    op.execute("DELETE FROM business_write_owners WHERE aggregate_key='identity'")
