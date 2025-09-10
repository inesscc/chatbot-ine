#!/usr/bin/env python3
"""
Script to load Parquet file into PostgreSQL database
"""

import pandas as pd
import psycopg2
from sqlalchemy import create_engine
import sys

def examine_parquet_file(file_path):
    """Examine the structure and content of the Parquet file"""
    print(f"Examining Parquet file: {file_path}")
    print("=" * 50)
    
    # Read the Parquet file
    df = pd.read_parquet(file_path)
    
    print(f"Shape: {df.shape} (rows, columns)")
    print(f"\nColumn names and types:")
    print(df.dtypes)
    print(f"\nFirst 5 rows:")
    print(df.head())
    print(f"\nBasic info:")
    print(df.info())
    print(f"\nMissing values:")
    print(df.isnull().sum())
    
    return df

def get_db_connection():
    """Get database connection configuration"""
    configs = [
        {
            "dbname": "toydb",
            "user": "toyuser",  # Using admin user for table creation
            "password": "toypass",
            "host": "localhost",
            "port": "5438",
        }
    ]
    
    for config in configs:
        try:
            conn = psycopg2.connect(**config)
            conn.close()
            return config
        except Exception as e:
            print(f"Connection failed with {config}: {e}")
            continue
    
    raise Exception("Could not connect to database")

def create_table_from_dataframe(df, table_name, db_config):
    """Create PostgreSQL table and insert data from DataFrame"""
    
    # Create SQLAlchemy engine
    connection_string = f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"
    engine = create_engine(connection_string)
    
    print(f"\nCreating table '{table_name}' and inserting data...")
    
    try:
        # Insert DataFrame into PostgreSQL
        # if_exists='replace' will drop the table if it exists and create a new one
        df.to_sql(table_name, engine, if_exists='replace', index=False, method='multi')
        print(f"✅ Successfully created table '{table_name}' with {len(df)} rows")
        
        # Verify the table was created
        with engine.connect() as conn:
            result = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = result.fetchone()[0]
            print(f"✅ Verified: Table '{table_name}' contains {count} rows")
            
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        return False
    
    return True

def update_allowed_tables(table_name):
    """Update the postgres_llm_tool.py to include the new table in ALLOWED_TABLES"""
    try:
        with open('postgres_llm_tool.py', 'r') as f:
            content = f.read()
        
        # Find the ALLOWED_TABLES line and add the new table
        old_line = 'ALLOWED_TABLES = ["users", "categories", "products", "orders", "order_items"]'
        new_line = f'ALLOWED_TABLES = ["users", "categories", "products", "orders", "order_items", "{table_name}"]'
        
        if old_line in content:
            content = content.replace(old_line, new_line)
            with open('postgres_llm_tool.py', 'w') as f:
                f.write(content)
            print(f"✅ Updated postgres_llm_tool.py to include '{table_name}' in allowed tables")
        else:
            print("⚠️  Could not automatically update ALLOWED_TABLES - please add manually")
            
    except Exception as e:
        print(f"⚠️  Could not update postgres_llm_tool.py: {e}")

def main():
    parquet_file = "data/ene_prueba_inicial.parquet"
    table_name = "ene_prueba_inicial"  # You can change this
    
    try:
        # Step 1: Examine the Parquet file
        df = examine_parquet_file(parquet_file)
        
        # Step 2: Get database connection
        db_config = get_db_connection()
        print(f"\n✅ Connected to database: {db_config['host']}:{db_config['port']}")
        
        # Step 3: Ask user confirmation
        print(f"\nReady to create table '{table_name}' with {len(df)} rows and {len(df.columns)} columns.")
        response = input("Proceed? (y/N): ").strip().lower()
        
        if response != 'y':
            print("Operation cancelled.")
            return
        
        # Step 4: Create table and insert data
        success = create_table_from_dataframe(df, table_name, db_config)
        
        if success:
            # Step 5: Update the LLM tool to include this table
            update_allowed_tables(table_name)
            
            print(f"\n🎉 Success! Your Parquet data is now available in PostgreSQL as table '{table_name}'")
            print(f"You can now query it using your LLM tool with questions like:")
            print(f"  - 'Show me the first 10 rows from {table_name}'")
            print(f"  - 'What columns are in the {table_name} table?'")
            print(f"  - 'How many records are in {table_name}?'")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
