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
    sql = re.sub(
        r"<think>\n.*?</think>(\n+)?", "", sql, flags=re.DOTALL
    )  # remove <think>...</think> blocks
    print("DEBUG: Validating SQL query:")
    print(f"{sql=}")
    print("-----------------------------------------------")
    # Must start with SELECT
    if not sql.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    # Block dangerous keywords/functions
    forbidden = [
        ";",
        "--",
        "pg_",
        "information_schema",
        "COPY",
        "ALTER",
        "DROP",
        "INSERT",
        "UPDATE",
        "DELETE",
        "SET",
    ]
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
        description="Procesando...",
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
ALLOWED_TABLES = ["total_unificado"]


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
                "port": "5432",  # Internal container port
            },
            {
                "dbname": "toydb",
                "user": "readonly_user",
                "password": "readonly_password",
                "host": "localhost",  # External host
                "port": "5438",  # Mapped port
            },
        ]

        for config in configs:
            try:
                # Test connection
                conn = psycopg2.connect(
                    dbname=config["dbname"],
                    user=config["user"],
                    password=config["password"],
                    host=config["host"],
                    port=config["port"],
                )
                conn.close()
                return config
            except Exception:
                continue

        # If all fail, return the localhost config as default
        return configs[1]

    async def get_indicator_metadata(
        self,
        indicator_name: str | None = None,
        __event_emitter__: Callable[[dict], Any] | None = None,
    ) -> str:
        """
        Get comprehensive metadata about available indicators in the database.

        Returns both structured JSON and natural language summary to help the LLM
        understand what data is available before generating SQL queries.

        For each indicator, provides:
        - Available years (min, max)
        - Available groupings (national, by sex, by region)
        - Frequency types (monthly, annual)
        - Sample query patterns

        :param __event_emitter__: Event emitter for updates (optional).
        :return: JSON string with comprehensive indicator metadata.
        """
        emitter = EventEmitter(__event_emitter__)

        try:
            await emitter.emit(
                description="Fetching indicator metadata from database...",
                status="fetching_metadata",
                done=False,
            )

            db_config = self.get_db_config()
            indicators_metadata = []

            # Indicator descriptions
            indicator_descriptions = {
                "tasa_desocupacion": "Tasa de desocupación",
                "tasa_ocupacion": "Tasa de ocupación",
                "tasa_participacion": "Tasa de participación laboral",
                "personas_fuerza_trabajo": "Personas en la fuerza de trabajo",
                "personas_edad_trabajar": "Población en edad de trabajar",
                "personas_ocupadas": "Población ocupada",
                "personas_desocupadas": "Población desocupada",
                "percepcion_aumento_delincuencia_pais": "Percepción de aumento de la delincuencia en el país",
                "victimizacion_hogares_delitos_mayor_connotacion_social": "Victimización de hogares por delitos de mayor connotación social",
                "victimizacion_hogares_delitos_violentos": "Victimización de hogares por delitos violentos",
                "victimizacion_personas_delitos_violentos": "Victimización de personas por delitos violentos",
            }

            with psycopg2.connect(
                dbname=db_config["dbname"],
                user=db_config["user"],
                password=db_config["password"],
                host=db_config["host"],
                port=db_config["port"],
            ) as conn:
                with conn.cursor() as cur:
                    # Get overall table info
                    table_name = ALLOWED_TABLES[0]


                    # Get list of all indicators (or filter if specified)
                    if indicator_name:
                        # Validate that the indicator exists
                        cur.execute(f"SELECT DISTINCT indicador FROM {table_name} WHERE indicador = %s", (indicator_name,))
                        result = cur.fetchone()
                        if not result:
                            # Fetch available indicators for error message
                            cur.execute(f"SELECT DISTINCT indicador FROM {table_name} ORDER BY indicador")
                            available = [row[0] for row in cur.fetchall()]

                            await emitter.emit(
                                description=f"Indicator '{indicator_name}' not found in database.",
                                status="indicator_not_found",
                                done=True,
                            )
                            return json.dumps({
                                "error": f"Indicator '{indicator_name}' not found",
                                "available_indicators": available
                            }, indent=2)
                        all_indicators = [indicator_name]
                    else:
                        cur.execute(f"SELECT DISTINCT indicador FROM {table_name} ORDER BY indicador")
                        all_indicators = [row[0] for row in cur.fetchall()]

                    # For each indicator, get detailed metadata
                    for indicador in all_indicators:
                        # Get basic stats
                        cur.execute(f"""
                            SELECT

                                MIN(año) as min_year,
                                MAX(año) as max_year
                            FROM {table_name}
                            WHERE indicador = %s
                        """, (indicador,))
                        min_year, max_year = cur.fetchone()

                        # Get available frequencies
                        cur.execute(f"""
                            SELECT DISTINCT frecuencia
                            FROM {table_name}
                            WHERE indicador = %s AND frecuencia IS NOT NULL
                            ORDER BY frecuencia
                        """, (indicador,))
                        frequencies = [row[0] for row in cur.fetchall()]

                        # Get grouping information
                        cur.execute(f"""
                            SELECT
                                grupo
                            FROM {table_name}
                            WHERE indicador = %s
                            GROUP BY grupo
                            ORDER BY grupo NULLS FIRST
                        """, (indicador,))
                        grouping_rows = cur.fetchall()
                        grouping_rows = [i[0] for i in grouping_rows]

                        groupings = []
                        for grupo  in grouping_rows:
                            if grupo is None:
                                groupings.append({
                                    "type": "national",
                                    "description": "National aggregated data (grupo IS NULL)"
                                })
                            else:

                                groupings.append({
                                    "type": grupo,

                                })

                        # Build query examples
                        query_examples = []
                        if "nacional" in [g["type"] for g in groupings] or any(g["type"] == "national" for g in groupings):
                            if "mensual" in frequencies:
                                query_examples.append(
                                    f"For national monthly data: WHERE indicador='{indicador}' AND grupo IS NULL AND frecuencia='mensual'"
                                )
                            if "anual" in frequencies:
                                query_examples.append(
                                    f"For national annual data: WHERE indicador='{indicador}' AND grupo IS NULL AND frecuencia='anual'"
                                )

                        for grp in groupings:
                            if grp["type"] == "sexo":
                                query_examples.append(
                                    f"For men's data: WHERE indicador='{indicador}' AND grupo='sexo' AND valor_grupo='hombre'"
                                )
                                break
                            elif grp["type"] == "region":
                                query_examples.append(
                                    f"For regional data (e.g., Metropolitana): WHERE indicador='{indicador}' AND grupo='region' AND valor_grupo='Metropolitana'"
                                )
                                break

                        # Build indicator metadata
                        indicators_metadata.append({
                            "name": indicador,
                            "description": indicator_descriptions.get(indicador, ""),
                            "time_coverage": {
                                "min_year": int(min_year) if min_year else None,
                                "max_year": int(max_year) if max_year else None,
                                "frequencies": frequencies
                            },
                            "groupings": groupings,
                            "query_examples": query_examples
                        })

                    # Get global grouping dimensions
                    cur.execute(f"""
                        SELECT DISTINCT valor_grupo
                        FROM {table_name}
                        WHERE grupo = 'sexo' AND valor_grupo IS NOT NULL
                        ORDER BY valor_grupo
                    """)
                    sexo_values = [row[0] for row in cur.fetchall()]

                    cur.execute(f"""
                        SELECT DISTINCT valor_grupo
                        FROM {table_name}
                        WHERE grupo = 'region' AND valor_grupo IS NOT NULL
                        ORDER BY valor_grupo
                    """)
                    

                    grouping_dimensions = {}
                    if 'sexo' in [g['type'] for g in groupings]:
                        grouping_dimensions["sexo"] = sexo_values
                    if 'region' in [g['type'] for g in groupings]:
                        region_values = [row[0] for row in cur.fetchall()]
                        grouping_dimensions["region"] = region_values

            # Build natural language summary
            summary_lines = ["Available Indicators:\n"]

            # Group by category
            employment_indicators = [ind for ind in indicators_metadata
                                      if ind["name"] in ["tasa_desocupacion", "tasa_ocupacion",
                                                         "tasa_participacion", "personas_fuerza_trabajo",
                                                         "poblacion_edad_trabajar"]]
            crime_indicators = [ind for ind in indicators_metadata
                                if ind["name"] not in ["tasa_desocupacion", "tasa_ocupacion",
                                                       "tasa_participacion", "personas_fuerza_trabajo",
                                                       "poblacion_edad_trabajar"]]

            if employment_indicators:
                summary_lines.append("Employment Indicators (ENE):")
                for ind in employment_indicators:
                    freqs = ", ".join(ind["time_coverage"]["frequencies"])
                    grouping_types = [g["type"] for g in ind["groupings"]]
                    summary_lines.append(
                        f"  - {ind['name']}: {ind['description']}. "
                        f"Data from {ind['time_coverage']['min_year']}-{ind['time_coverage']['max_year']}. "
                        #f"Available {freqs}. Groupings: {', '.join(grouping_types)}"
                    )
                summary_lines.append("")

            if crime_indicators:
                summary_lines.append("Crime/Security Indicators (ENUSC):")
                for ind in crime_indicators:
                    freqs = ", ".join(ind["time_coverage"]["frequencies"])
                    grouping_types = [g["type"] for g in ind["groupings"]]
                    summary_lines.append(
                        f"  - {ind['name']}: {ind['description']}. "
                        f"Data from {ind['time_coverage']['min_year']}-{ind['time_coverage']['max_year']}. "
                        #f"Available {freqs}. Groupings: {', '.join(grouping_types)}"
                    )
                summary_lines.append("")

            if indicator_name:
                summary_lines.append("Key SQL Patterns:")
                summary_lines.append("  - For national/total data: grupo IS NULL AND valor_grupo IS NULL")
                summary_lines.append("  - For sex-disaggregated data: grupo='sexo' AND valor_grupo IN ('hombre', 'mujer')")
                summary_lines.append("  - For regional data: grupo='region' AND valor_grupo IN (region names like 'Metropolitana', 'Valparaíso', etc.)")
                summary_lines.append("  - For monthly data: frecuencia='mensual'")
                summary_lines.append("  - For annual data: frecuencia='anual'")

            summary = "\n".join(summary_lines)

            # Build final result
            result = {
                #"table_name": table_name,
                "summary": summary,
                "indicators": indicators_metadata,
                "grouping_dimensions": grouping_dimensions
            }

            if not indicator_name:
                result = result["summary"]

            formatted_result = json.dumps(result, indent=2, default=str)

            await emitter.emit(
                description="Successfully retrieved indicator metadata.",
                content=formatted_result,
                status="metadata_fetched",
                done=True,
            )

            return formatted_result

        except Exception as e:
            await emitter.emit(
                description=f"Error fetching indicator metadata: {str(e)}",
                status="fetch_error",
                done=True,
            )
            return f"Error fetching indicator metadata: {e}"

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

        Table: total_unificado
        Columns: (indicador, valor_indicador, grupo, valor_grupo, año, mes, frecuencia)

        Schema Description:
        This table contains unified Chilean indicators from multiple sources (employment survey ENE and crime/security survey ENUSC).
        It uses a flexible grouping structure to support both aggregated and disaggregated data.

        Column Descriptions:
        - indicador: Type of metric (e.g., tasa_desocupacion, personas_fuerza_trabajo, percepcion_aumento_delincuencia_pais)
        - valor_indicador: Numerical value of the indicator
        - grupo: Grouping category (NULL for national data, 'sexo' for sex-disaggregated, 'region' for regional)
        - valor_grupo: Value within the group (NULL for national, 'hombre'/'mujer' for sex, region names like 'Metropolitana', 'Valparaíso', etc. for regions)
        - año: Year (integer)
        - mes: Month number ('1'-'12' for monthly data, NULL for annual data)
        - frecuencia: Data frequency ('mensual' or 'anual')

        Sample Data:
        indicador: personas_fuerza_trabajo, valor_indicador: 4808.37, grupo: sexo, valor_grupo: hombre, año: 2010, mes: None, frecuencia: anual
        indicador: personas_fuerza_trabajo, valor_indicador: 3191.70, grupo: sexo, valor_grupo: mujer, año: 2010, mes: None, frecuencia: anual
        indicador: personas_fuerza_trabajo, valor_indicador: 7883.69, grupo: NULL, valor_grupo: NULL, año: 2010, mes: 1, frecuencia: mensual
        indicador: tasa_participacion, valor_indicador: 59.66, grupo: NULL, valor_grupo: NULL, año: 2022, mes: 4, frecuencia: mensual

        Available Indicators:
        Employment Indicators (ENE):
        - tasa_desocupacion (unemployment rate)
        - tasa_ocupacion (employment rate)
        - tasa_participacion (labor force participation rate)
        - personas_fuerza_trabajo (people in workforce)
        - poblacion_edad_trabajar (working age population)

        Crime/Security Indicators (ENUSC):
        - percepcion_aumento_delincuencia_pais (perception of crime increase)
        - victimizacion_hogares_delitos_mayor_connotacion_social (household victimization - major crimes)
        - victimizacion_hogares_delitos_violentos (household victimization - violent crimes)
        - victimizacion_personas_delitos_violentos (personal victimization - violent crimes)

        CRITICAL SQL Patterns (you MUST use these exact patterns):
        - For national/total data: WHERE grupo IS NULL AND valor_grupo IS NULL
        - For sex-disaggregated data: WHERE grupo = 'sexo' AND valor_grupo IN ('hombre', 'mujer')
        - For regional data: WHERE grupo = 'region' AND valor_grupo IN (region names like 'Metropolitana', 'Valparaíso', 'Biobío', etc.)
        - For monthly data: WHERE frecuencia = 'mensual' AND mes IS NOT NULL
        - For annual data: WHERE frecuencia = 'anual' AND mes IS NULL

        Query Guidelines:
        - NEVER use = NULL or != NULL. ALWAYS use IS NULL or IS NOT NULL for NULL comparisons
        - NEVER use aggregating functions like SUM or COUNT
        - When comparing groups, use appropriate WHERE conditions on grupo and valor_grupo
        - Remember that NULL values require IS NULL / IS NOT NULL operators

        Available tables: {", ".join(ALLOWED_TABLES)}
        User Query: {natural_language_query}

        Reply ONLY with the SQL SELECT command, no additional text is permitted.
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
                            content=f"Respuesta parcial recibida: {chunk.get('response', '')}",
                            status="sql_generation_in_progress",
                            done=False,
                        )

                        # Break if the stream indicates completion
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError as e:
                        await emitter.emit(
                            description=f"Error procesando JSON en streaming: {e}",
                            status="json_parse_error",
                            done=True,
                        )
                        return f"Error procesando JSON en streaming: {e}"
                return sql_query

        try:
            # Use asyncio to run the asynchronous request
            await emitter.emit(
                description="Generando comando SQL a partir de la consulta en lenguaje natural...",
                status="sql_generation_in_progress",
                done=False,
            )

            sql_query = await send_request()
            if not sql_query:
                raise ValueError("No SQL query was returned by the LLM.")

            await emitter.emit(
                description="Comando SQL generado exitosamente.",
                status="sql_generated",
                done=True,
            )

            return sql_query  # Return the SQL query
        except Exception as e:
            await emitter.emit(
                description=f"Error al instruir al LLM para generar SQL: {e}",
                status="query_error",
                done=True,
            )
            return f"Error al instruir al LLM para generar SQL: {e}"
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
                description="Generando comando SQL a partir de la consulta en lenguaje natural...",
                status="sql_generation_in_progress",
                done=False,
            )
            sql_query = await self.instruct_llm_to_generate_sql(
                natural_language_query, __event_emitter__
            )
            print(f"DEBUG: Generated SQL Query:\n{sql_query} -------------------------")

            if not sql_query:
                raise ValueError("Generated SQL query is empty.")

            await emitter.emit(
                description=f"Comando SQL generado: {sql_query}",
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
                port=db_config["port"],
            ) as conn:
                with conn.cursor() as cur:
                    # Use your database's allowed tables
                    safe_query = validate_sql(
                        sql_query, allowed_tables=ALLOWED_TABLES, max_limit=100
                    )
                    cur.execute(safe_query)
                    rows = cur.fetchall()

                    # Get column names for formatting results
                    if cur.description is not None:
                        column_names = [desc[0] for desc in cur.description]
                        results = [dict(zip(column_names, row)) for row in rows]
                    else:
                        # This should never happen after a successful execute, but satisfies type checker
                        results = [list(row) for row in rows]
                    
                    if results == []:
                        results = [{"message": "Query didn't return any results. Try get_indicator_metadata to see available\
                                     indicators and groupings for each indicator"}]
                    results.append({'used_query': safe_query})
                    
                    formatted_results = json.dumps(results, indent=2, default=str)

                    # Step 3: Emit success message with results
                    await emitter.emit(
                        description="Comando SQL ejecutado exitosamente.",
                        content=formatted_results,
                        status="query_success",
                        done=True,
                    )

                    return formatted_results

        except Exception as e:
            await emitter.emit(
                description=f"Error durante la ejecución de la consulta: {str(e)}",
                status="query_error",
                done=True,
            )
            return f"Error ejecutando la consulta: {e}"

# Example usage function for testing
async def test_tool():
    """Test the database tool with sample queries"""
    tool = Tools()

    # Test queries
    test_queries = [
        "proporción de hogares victimizados por delitos violentos en la región de Tarapacá durante julio de 2023",
        "What categories do we have?",
        "Show me products with their categories",
        "How many orders are there?",
    ]

    for query in test_queries:
        print(f"\n--- Testing: {query} ---")
        #res1 = await tool.get_indicator_metadata(indicator_name='victimizacion_hogares_delitos_violentos')
        result = await tool.execute_query(query)
        print(result)


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_tool())
