-- step 1: ensure target database exists
DO
$$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_database WHERE datname = 'peepamemory'
   ) THEN
      PERFORM dblink_exec(
         'dbname=' || current_database(),
         'CREATE DATABASE peepamemory
            WITH OWNER = postgres
            ENCODING = ''UTF8''
            LC_COLLATE = ''C''
            LC_CTYPE = ''C''
            TEMPLATE template0');
   END IF;
END
$$;

-- step 2: connect to the target database
\c peepamemory

-- step 3: enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
