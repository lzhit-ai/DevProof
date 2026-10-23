package ai.devproof.migration;

import ai.devproof.infrastructure.Json;
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.LoggerContext;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.sql.*;
import java.util.*;
import org.flywaydb.core.Flyway;
import org.slf4j.LoggerFactory;

/** The deployment migration entry; normal Spring startup never calls migrate or baseline. */
public final class SchemaMigrations {
    public static final String VERSION="62";
    public static final String LEGACY_HEAD="059_java_security_profiles";
    public static final long LOCK=6000592026L;
    private static final Set<String> WRITERS=Set.of("reports","verification-inputs","verification","identity","projects","task-management","github-sources","knowledge-bases","knowledge-sources","orchestration","evidence-materials","git-inputs","delivery-associations","delivery-claims","evidence-questions","project-status","security-baselines","peripheral-profiles");
    private SchemaMigrations() {}
    private static final class Failure extends RuntimeException { Failure(String code) { super(code); } }
    public static int run(String[] args) {
        // Flyway's ordinary INFO logs include the JDBC URL; deployment output contains stable codes only.
        if(LoggerFactory.getILoggerFactory() instanceof LoggerContext logging)logging.getLogger("org.flywaydb").setLevel(Level.OFF);
        if(args.length!=2 || !Set.of("migrate","handoff-alembic","validate").contains(args[1])) { System.err.println("Usage: db migrate|handoff-alembic|validate");return 2; }
        try { execute(args[1]);return 0; }
        catch(Failure failure) { System.err.println(failure.getMessage());return 2; }
        catch(SQLException failure) { System.err.println("SCHEMA_SQL_FAILED SQLSTATE="+failure.getSQLState());return 1; }
        catch(Exception failure) { System.err.println("SCHEMA_MIGRATION_FAILED type="+failure.getClass().getSimpleName());return 1; }
    }
    private static void execute(String mode) throws Exception {
        String url=required("JAVA_DATABASE_URL"),user=required("POSTGRES_USER"),password=required("POSTGRES_PASSWORD");
        try(var connection=DriverManager.getConnection(url,user,password)) {
            scalar(connection,"SET search_path TO public");
            if(!Boolean.TRUE.equals(scalar(connection,"SELECT pg_try_advisory_lock("+LOCK+")")))throw new Failure("SCHEMA_MIGRATION_BUSY");
            try {
                if("validate".equals(mode)) { requireCurrent(connection);flyway(url,user,password,null).validate();System.out.println("FLYWAY_SCHEMA_VALID version="+VERSION);return; }
                boolean history=exists(connection,"flyway_schema_history"),marker=exists(connection,"schema_migration_ownership");
                if(marker)requireOwner(connection);
                else if(exists(connection,"alembic_version")) {
                    if(!LEGACY_HEAD.equals(scalar(connection,"SELECT version_num FROM alembic_version")))throw new Failure("ALEMBIC_HEAD_UNSUPPORTED");
                    requireCatalog(connection);
                    if(!history) {
                        if(!"handoff-alembic".equals(mode))throw new Failure("EXPLICIT_ALEMBIC_HANDOFF_REQUIRED");
                        handoffWriters(connection);
                        flyway(url,user,password,null).baseline();
                        System.out.println("ALEMBIC_BASELINED version=59");
                    } else {
                        var current=flyway(url,user,password,null).info().current();
                        if(current==null || !"59".equals(current.getVersion().toString()))throw new Failure("INCOMPLETE_FLYWAY_STATE");
                        requireWriters(connection,false);
                    }
                } else {
                    if("handoff-alembic".equals(mode))throw new Failure("EMPTY_SCHEMA_USE_MIGRATE");
                    long objects=((Number)scalar(connection,"SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname<>'flyway_schema_history' AND c.relkind IN ('r','p','v','m','S','f')) + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public')")).longValue();
                    if(objects!=0)throw new Failure("NONEMPTY_SCHEMA_WITHOUT_SUPPORTED_HISTORY");
                    flyway(url,user,password,"59").migrate();
                    requireCatalog(connection);requireWriters(connection,false);
                    System.out.println("FRESH_SCHEMA_CREATED version=59");
                }
                flyway(url,user,password,null).migrate();requireCurrent(connection);flyway(url,user,password,null).validate();
                System.out.println("FLYWAY_SCHEMA_READY version="+VERSION);
            } finally { scalar(connection,"SELECT pg_advisory_unlock("+LOCK+")"); }
        }
    }
    private static Flyway flyway(String url,String user,String password,String target) {
        var config=Flyway.configure().dataSource(url,user,password).defaultSchema("public").schemas("public")
            .locations("classpath:db/migration").baselineVersion("59").baselineDescription("Reviewed Alembic 059 schema")
            .baselineOnMigrate(false).cleanDisabled(true).validateMigrationNaming(true).loggers("slf4j");
        if(target!=null)config.target(target);return config.load();
    }
    private static void handoffWriters(Connection connection) throws SQLException {
        connection.setAutoCommit(false);
        try {
            requireWriters(connection,true);
            long active=((Number)scalar(connection,"""
                SELECT (SELECT count(*) FROM analysis_runs WHERE executor_owner='PYTHON' AND run_status IN ('QUEUED','RUNNING'))
                  + (SELECT count(*) FROM source_sync_runs WHERE executor_owner='PYTHON' AND status='RUNNING')
                  + (SELECT count(*) FROM source_ingestion_jobs WHERE executor_owner='PYTHON' AND job_status IN ('QUEUED','RUNNING'))
                  + (SELECT count(*) FROM retrieval_index_build_runs WHERE executor_owner='PYTHON' AND status IN ('QUEUED','RUNNING'))
                """)).longValue();
            if(active!=0)throw new Failure("LEGACY_EXECUTIONS_MUST_DRAIN");
            try(var statement=connection.createStatement()) { statement.executeUpdate("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE owner<>'JAVA'"); }
            connection.commit();System.out.println("BUSINESS_WRITERS_CONFIRMED count="+WRITERS.size());
        } catch(RuntimeException|SQLException failure) { connection.rollback();throw failure; }
        finally { connection.setAutoCommit(true); }
    }
    private static void requireWriters(Connection connection,boolean lock) throws SQLException {
        var found=new HashSet<String>();
        try(var statement=connection.createStatement();var rows=statement.executeQuery("SELECT aggregate_key,owner FROM business_write_owners ORDER BY aggregate_key"+(lock?" FOR UPDATE":""))) {
            while(rows.next()) { found.add(rows.getString(1));if(!lock && !"JAVA".equals(rows.getString(2)))throw new Failure("BUSINESS_WRITER_HANDOFF_INCOMPLETE"); }
        }
        if(!WRITERS.equals(found))throw new Failure("BUSINESS_WRITER_CATALOG_MISMATCH");
    }
    private static void requireCatalog(Connection connection) throws SQLException,IOException {
        var values=new ArrayList<Map<String,Object>>();
        try(var statement=connection.createStatement();var rows=statement.executeQuery(resource("db/baseline/catalog.sql"))) {
            while(rows.next())values.add(Map.of("kind",rows.getString(1),"identity",rows.getString(2),"definition",rows.getString(3)));
        }
        var accepted=Json.object(resource("db/baseline/catalog-accepted-v2.json"));String actual=Json.hash(Json.canonical(values));
        if(!Integer.valueOf(2).equals(accepted.get("catalogVersion")) || !Set.of(accepted.get("alembic"),accepted.get("restored")).contains(actual))throw new Failure("SCHEMA_BASELINE_MISMATCH_REVIEW_DATABASE_STRUCTURE");
        System.out.println("SCHEMA_BASELINE_MATCHED definitions="+values.size()+" variant="+(actual.equals(accepted.get("alembic"))?"ALEMBIC":"RESTORED"));
    }
    private static void requireCurrent(Connection connection) throws SQLException,IOException {
        if(!exists(connection,"flyway_schema_history") || !exists(connection,"schema_migration_ownership"))throw new Failure("FLYWAY_SCHEMA_NOT_READY");
        if(!VERSION.equals(scalar(connection,"SELECT version FROM flyway_schema_history WHERE success AND version IS NOT NULL ORDER BY installed_rank DESC LIMIT 1")))throw new Failure("FLYWAY_VERSION_MISMATCH");
        requireOwner(connection);
    }
    public static int writerCount() { return WRITERS.size(); }
    private static void requireOwner(Connection connection) throws SQLException,IOException {
        try(var statement=connection.createStatement();var rows=statement.executeQuery("SELECT owner,baseline_revision,baseline_catalog_hash FROM schema_migration_ownership WHERE id=true")) {
            if(!rows.next() || !"FLYWAY".equals(rows.getString(1)) || !LEGACY_HEAD.equals(rows.getString(2)) || !resource("db/baseline/catalog.sha256").strip().equals(rows.getString(3)))throw new Failure("SCHEMA_OWNER_MISMATCH");
        }
        requireWriters(connection,false);
    }
    private static boolean exists(Connection connection,String table) throws SQLException { return Boolean.TRUE.equals(scalar(connection,"SELECT to_regclass('public."+table+"') IS NOT NULL")); }
    private static Object scalar(Connection connection,String sql) throws SQLException {
        try(var statement=connection.createStatement()) { if(!statement.execute(sql))return null;try(var rows=statement.getResultSet()) { return rows.next()?rows.getObject(1):null; } }
    }
    private static String resource(String name) throws IOException {
        try(var stream=SchemaMigrations.class.getClassLoader().getResourceAsStream(name)) { if(stream==null)throw new Failure("MIGRATION_RESOURCE_MISSING");return new String(stream.readAllBytes(),StandardCharsets.UTF_8); }
    }
    private static String required(String name) { String value=System.getenv(name);if(value==null || value.isBlank())throw new Failure("MISSING_MIGRATION_CONFIGURATION "+name);return value; }
}
