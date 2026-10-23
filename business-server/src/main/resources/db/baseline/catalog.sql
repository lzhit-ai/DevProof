-- Definitions only: data, object owners, ACLs and extension-owned objects are excluded.
WITH tables AS (
  SELECT c.oid,c.relname,c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S')
    AND c.relname NOT IN ('flyway_schema_history','schema_migration_ownership')
    AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e')
), entries(kind,identity,definition) AS (
  SELECT 'relation',relname::text,relkind::text || ':' || relpersistence::text || ':' || relrowsecurity::text || ':' || relforcerowsecurity::text FROM tables
  UNION ALL
  SELECT 'column',c.relname || '.' || a.attname,
    a.attnum::text || ':' || format_type(a.atttypid,a.atttypmod) || ':' || a.attnotnull::text || ':' || a.attidentity::text || ':' || a.attgenerated::text || ':' || coalesce(pg_get_expr(d.adbin,d.adrelid),'') || ':' || a.attcollation::regcollation::text
  FROM tables c JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
  LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
  UNION ALL
  SELECT 'constraint',c.relname || '.' || k.conname,pg_get_constraintdef(k.oid,true) || ':' || k.convalidated::text
  FROM tables c JOIN pg_constraint k ON k.conrelid=c.oid
  UNION ALL
  SELECT 'index',i.relname,pg_get_indexdef(i.oid) FROM tables c JOIN pg_index x ON x.indrelid=c.oid JOIN pg_class i ON i.oid=x.indexrelid
  UNION ALL
  SELECT 'trigger',c.relname || '.' || t.tgname,pg_get_triggerdef(t.oid,true) || ':' || t.tgenabled::text FROM tables c JOIN pg_trigger t ON t.tgrelid=c.oid WHERE NOT t.tgisinternal
  UNION ALL
  SELECT 'view',c.relname,pg_get_viewdef(c.oid,true) FROM tables c WHERE c.relkind IN ('v','m')
  UNION ALL
  SELECT 'function',p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',pg_get_functiondef(p.oid)
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind IN ('f','p')
    AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')
  UNION ALL
  SELECT 'extension',e.extname,n.nspname || ':' || e.extversion FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname<>'plpgsql'
  UNION ALL
  SELECT 'policy',c.relname || '.' || p.polname,coalesce(pg_get_expr(p.polqual,p.polrelid),'') || ':' || coalesce(pg_get_expr(p.polwithcheck,p.polrelid),'') FROM tables c JOIN pg_policy p ON p.polrelid=c.oid
  UNION ALL
  SELECT 'type',t.typname,t.typtype::text FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
  LEFT JOIN pg_class c ON c.oid=t.typrelid
  WHERE n.nspname='public' AND (t.typtype IN ('d','e','r','m') OR c.relkind='c')
    AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_type'::regclass AND d.objid=t.oid AND d.deptype='e')
  UNION ALL
  SELECT 'namespace',nspname,'custom' FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%'
)
SELECT kind,identity,definition FROM entries ORDER BY kind COLLATE "C",identity COLLATE "C",definition COLLATE "C";
