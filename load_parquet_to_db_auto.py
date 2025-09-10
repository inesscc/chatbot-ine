#!/usr/bin/env python3
"""
Automated script to load Parquet file into PostgreSQL database during initialization
"""

import pandas as pd
import psycopg2
from sqlalchemy import create_engine, text
import time
import sys
import os

def wait_for_db():
    """Wait for database to be ready"""
    max_retries = 30
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            conn = psycopg2.connect(
                dbname="toydb",
                user="toyuser",
                password="toypass",
                host="localhost",
                port="5432"
            )
            conn.close()
            print("✅ Database is ready!")
            return True
        except Exception as e:
            print(f"Waiting for database... ({retry_count + 1}/{max_retries})")
            time.sleep(2)
            retry_count += 1
    
    print("❌ Database not ready after maximum retries")
    return False

def load_parquet_data():
    """Load Parquet data into PostgreSQL"""
    parquet_file = "/data/ene_prueba_inicial.parquet"
    table_name = "ene_prueba_inicial"
    
    if not os.path.exists(parquet_file):
        print(f"❌ Parquet file not found: {parquet_file}")
        return False
    
    try:
        # Read Parquet file
        print(f"📖 Reading Parquet file: {parquet_file}")
        df = pd.read_parquet(parquet_file)
        print(f"📊 Data shape: {df.shape} (rows, columns)")
        
        # Create database connection
        connection_string = "postgresql://toyuser:toypass@localhost:5432/toydb"
        engine = create_engine(connection_string)
        
        # Load data into PostgreSQL
        print(f"💾 Loading data into table '{table_name}'...")
        df.to_sql(table_name, engine, if_exists='replace', index=False, method='multi')
        
        # Grant permissions to readonly user
        with engine.connect() as conn:
            conn.execute(text(f"GRANT SELECT ON {table_name} TO readonly_user"))
            conn.commit()
        
        print(f"✅ Successfully loaded {len(df)} rows into table '{table_name}'")
        return True
        
    except Exception as e:
        print(f"❌ Error loading Parquet data: {e}")
        return False

def main():
    print("🚀 Starting Parquet data loader...")
    
    # Wait for database to be ready
    if not wait_for_db():
        sys.exit(1)
    
    # Load Parquet data
    if load_parquet_data():
        print("🎉 Parquet data loading completed successfully!")
    else:
        print("💥 Parquet data loading failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
