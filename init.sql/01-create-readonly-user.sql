-- Create a read-only user for the database
-- This script runs during PostgreSQL container initialization

-- Create the read-only user
CREATE USER readonly_user WITH PASSWORD 'readonly_password';

-- Grant CONNECT privilege to the database
GRANT CONNECT ON DATABASE toydb TO readonly_user;

-- Grant USAGE on the public schema
GRANT USAGE ON SCHEMA public TO readonly_user;

-- Grant SELECT on all existing tables in the public schema
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- Grant SELECT on all future tables in the public schema
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- Grant USAGE on all existing sequences (needed for tables with SERIAL columns)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO readonly_user;

-- Grant USAGE on all future sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO readonly_user;

-- Optional: If you have other schemas, you can add similar grants for them
-- GRANT USAGE ON SCHEMA other_schema TO readonly_user;
-- GRANT SELECT ON ALL TABLES IN SCHEMA other_schema TO readonly_user;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA other_schema GRANT SELECT ON TABLES TO readonly_user;
