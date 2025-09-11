"""
title: Postgres Database Tool
author: Juan Concha (adapted from Joshua Rudy)
version: 0.0.1
license: MIT
description: A simple tool for interacting with a PostgreSQL database. Ask the model questions and it will take the request
and pass it as an API call to Ollama to generate a SQL query before executing the query using psycopg2. 
Added safe guards with query validations. Caution should be exercised anyways. Use an adjust as you need. 
I want to take the DB_CONFIG and make it global, it's unnecessary to define twice, but it works for now.
I intend to take this and work it into a filter function or pipe for RAG and general DB interaction.

This version hardcodes the database schema in the prompt. Could be moved to the system prompt, but haven't
tested performance in that case.

Adapted for docker environment with:
- toydb database
- readonly_user for safe queries
- localhost:5438 connection
- Updated table whitelist for your schema
"""

import json
from typing import Callable, Any
import re
import httpx
import requests
import asyncio
import psycopg2

def validate_sql(sql_query: str, allowed_tables=None, max_limit=100) -> str:
    """
    Validate and sanitize an SQL query before execution.
    
    - Only allows SELECT queries
    - Blocks access to system tables/functions
    - Ensures only whitelisted tables are queried
    - Forces a LIMIT if not present
    
    :param sql_query: SQL string from the LLM
    :param allowed_tables: list of allowed table names (default: None = allow all)
    :param max_limit: max number of rows to allow in results
    :return: safe SQL query (possibly modified with LIMIT)
    :raises ValueError: if query is unsafe
    """
    
    sql = sql_query.strip().rstrip(";")  # remove trailing semicolon
    sql = re.sub(r'<think>\n.*?</think>(\n+)?', '', sql, flags=re.DOTALL)  # remove <think>...</think> blocks
    print('DEBUG: Validating SQL query:')
    print(f'{sql=}')
    print('-----------------------------------------------')
    # Must start with SELECT
    if not sql.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    # Block dangerous keywords/functions
    forbidden = [";", "--", "pg_", "information_schema", "COPY", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE", "SET"]
    for word in forbidden:
        if re.search(rf"\b{word}\b", sql, flags=re.IGNORECASE):
            raise ValueError(f"Forbidden keyword detected: {word}")

    # Enforce table whitelist if provided
    if allowed_tables:
        found_tables = re.findall(r"FROM\s+([a-zA-Z0-9_\.]+)", sql, flags=re.IGNORECASE)
        for tbl in found_tables:
            if tbl not in allowed_tables:
                raise ValueError(f"Querying table '{tbl}' is not allowed")

    # Enforce LIMIT
    if not re.search(r"\bLIMIT\b", sql, flags=re.IGNORECASE):
        sql += f" LIMIT {max_limit}"

    return sql


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] | None = None):
        self.event_emitter = event_emitter

    async def emit(
        self,
        description="Processing...",
        status="in_progress",
        content="",
        message=None,
        done=False,
    ):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "content": content,
                        "message": message,
                        "done": done,
                    },
                }
            )


# Allowed tables in your database schema
ALLOWED_TABLES = ["ene_prueba_inicial"]


class Tools:
    def __init__(self):
        pass

    def get_db_config(self):
        """
        Get database configuration with fallback for different environments.
        Tries container name first (for running inside Docker), then localhost.
        """
        configs = [
            {
                "dbname": "toydb",
                "user": "readonly_user", 
                "password": "readonly_password",
                "host": "toy-postgres",  # Container name
                "port": "5432",          # Internal container port
            },
            {
                "dbname": "toydb",
                "user": "readonly_user", 
                "password": "readonly_password",
                "host": "localhost",     # External host
                "port": "5438",          # Mapped port
            }
        ]
        
        for config in configs:
            try:
                # Test connection
                conn = psycopg2.connect(
                    dbname=config["dbname"],
                    user=config["user"],
                    password=config["password"],
                    host=config["host"],
                    port=config["port"]
                )
                conn.close()
                return config
            except Exception:
                continue
        
        # If all fail, return the localhost config as default
        return configs[1]

    async def instruct_llm_to_generate_sql(
        self,
        natural_language_query: str,
        __event_emitter__: Callable[[dict], Any] | None = None,
    ) -> str:
        """
        Generate an SQL query from a natural language query.

        :param natural_language_query: The user's query in plain language.
        :param __event_emitter__: Event emitter for updates (optional).
        :return: The generated SQL query as a string.
        """
        emitter = EventEmitter(__event_emitter__)
        
        # Enhanced prompt with your database schema information
        prompt = f"""
        You are an assistant that converts natural language into SQL commands.
        Convert the following natural language query into an SQL command.

        Database Schema:
        - ene_prueba_inicial (indicador, anio, trimestre, valor, mes_string, mes, fecha)
        
        Table Context:
        The ene_prueba_inicial table contains Chilean employment survey data with the following structure:
        
        Sample data (first 2 rows):
        indicador: tasa_desocupacion, anio: 2010, trimestre: Ene - Mar, valor: 9.227598063619205, mes_string: ene, mes: 1, fecha: 2010-1
        indicador: tasa_desocupacion, anio: 2010, trimestre: Feb - Abr, valor: 8.836054099283027, mes_string: feb, mes: 2, fecha: 2010-2
        
        Available indicators (unique values in 'indicador' column):
        - tasa_desocupacion (unemployment rate)
        - tasa_ocupacion (employment rate) 
        - tasa_participacion (participation rate)
        - personas_fuerza_trabajo (people in workforce)
        - poblacion_edad_trabajar (working age population)
        
        Column descriptions:
        - indicador: type of employment metric
        - anio: year
        - trimestre: quarter period (e.g., "Ene - Mar" for Jan-Mar)
        - valor: numerical value of the indicator
        - mes_string: month name in Spanish
        - mes: month number (1-12)
        - fecha: date in YYYY-M format

        Available tables: {", ".join(ALLOWED_TABLES)}
        User Query: {natural_language_query}

        Reply ONLY with the SQL SELECT command, no additional text is permitted.
        Use proper JOIN syntax when querying related tables.
        """

        # Step 1: Get the available models from Ollama
        ollama_url = "http://localhost:11434"
        url = f"{ollama_url}/api/ps"

        try:
            # Make the request to fetch models
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for HTTP errors

            # Parse the JSON response
            models_data = response.json().get("models", [])

            # Extract model names and select the first available model
            model_names = [
                model.get("name") for model in models_data if "name" in model
            ]
            if not model_names:
                raise ValueError("No models available on the Ollama server.")
            model = model_names[0]

        except requests.RequestException as e:
            await emitter.emit(
                description=f"Error fetching models from Ollama: {e}",
                status="model_fetch_error",
                done=True,
            )
            return f"Error fetching models from Ollama: {e}"
        except ValueError as e:
            await emitter.emit(
                description=f"Error parsing models response: {e}",
                status="model_parse_error",
                done=True,
            )
            return f"Error parsing models response: {e}"

        # Step 2: Prepare the payload for generating the SQL query
        payload = {
            "model": model,  # Model name
            "prompt": prompt,  # Prompt to send to Ollama
        }

        headers = {"Content-Type": "application/json"}

        async def send_request():
            """
            Asynchronous function to handle streaming response from the LLM.
            """
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()  # Raise an error for bad responses

                sql_query = ""  # Concatenate response chunks here
                async for line in response.aiter_lines():
                    try:
                        # Parse each line as a JSON object
                        chunk = json.loads(line)
                        sql_query += chunk.get("response", "")

                        # Emit progress for debugging or user feedback
                        await emitter.emit(
                            content=f"Partial response received: {chunk.get('response', '')}",
                            status="sql_generation_in_progress",
                            done=False,
                        )

                        # Break if the stream indicates completion
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError as e:
                        await emitter.emit(
                            description=f"Error parsing streaming JSON: {e}",
                            status="json_parse_error",
                            done=True,
                        )
                        return f"Error parsing streaming JSON: {e}"

                return sql_query

        try:
            # Use asyncio to run the asynchronous request
            await emitter.emit(
                description="Generating SQL command from the natural language query...",
                status="sql_generation_in_progress",
                done=False,
            )

            sql_query = await send_request()
            if not sql_query:
                raise ValueError("No SQL query was returned by the LLM.")

            await emitter.emit(
                description="SQL query generated successfully.",
                status="sql_generated",
                done=True,
            )

            return sql_query  # Return the SQL query
        except Exception as e:
            await emitter.emit(
                description=f"Error while instructing LLM to generate SQL: {e}",
                status="query_error",
                done=True,
            )
            return f"Error while instructing LLM to generate SQL: {e}"

    async def execute_query(
        self,
        natural_language_query: str,
        __event_emitter__: Callable[[dict], Any] | None = None,
    ) -> str:
        """
        Executes a dynamically generated SQL query based on a natural language input.

        :param natural_language_query: The user's query in plain language.
        :param __event_emitter__: Event emitter for updates.
        :return: A string representation of the query results or an error message.
        """
        emitter = EventEmitter(__event_emitter__)

        try:
            # Step 1: Generate the SQL command
            await emitter.emit(
                description="Generating SQL command from the natural language query...",
                status="sql_generation_in_progress",
                done=False,
            )
            sql_query = await self.instruct_llm_to_generate_sql(
                natural_language_query, __event_emitter__
            )

            if not sql_query:
                raise ValueError("Generated SQL query is empty.")

            await emitter.emit(
                description=f"Generated SQL: {sql_query}",
                status="sql_generated",
                done=False,
            )

            # Step 2: Execute the SQL command using DB config
            db_config = self.get_db_config()
            with psycopg2.connect(
                dbname=db_config["dbname"],
                user=db_config["user"],
                password=db_config["password"],
                host=db_config["host"],
                port=db_config["port"]
            ) as conn:
                with conn.cursor() as cur:
                    # Use your database's allowed tables
                    safe_query = validate_sql(sql_query, allowed_tables=ALLOWED_TABLES, max_limit=100)
                    cur.execute(safe_query)
                    rows = cur.fetchall()

                    # Get column names for formatting results
                    if cur.description is not None:
                        column_names = [desc[0] for desc in cur.description]
                        results = [dict(zip(column_names, row)) for row in rows]
                    else:
                        # This should never happen after a successful execute, but satisfies type checker
                        results = [list(row) for row in rows]

                    formatted_results = json.dumps(results, indent=2, default=str)

                    # Step 3: Emit success message with results
                    await emitter.emit(
                        description="SQL command executed successfully.",
                        content=formatted_results,
                        status="query_success",
                        done=True,
                    )

                    return formatted_results

        except Exception as e:
            await emitter.emit(
                description=f"Error during query execution: {str(e)}",
                status="query_error",
                done=True,
            )
            return f"Error executing query: {e}"


# Example usage function for testing
async def test_tool():
    """Test the database tool with sample queries"""
    tool = Tools()
    
    # Test queries
    test_queries = [
        "Show me all users",
        "What categories do we have?",
        "Show me products with their categories",
        "How many orders are there?",
    ]
    
    for query in test_queries:
        print(f"\n--- Testing: {query} ---")
        result = await tool.execute_query(query)
        print(result)


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_tool())
