#!/usr/bin/env python3
"""
Unify ene_prueba_inicial.parquet and ene_sexo_prueba_inicial.parquet into a single table.

Target structure:
    indicador | valor_indicador | grupo | valor_grupo | año | mes
"""

import pandas as pd
import os
import numpy as np
from pathlib import Path
# Get the directory where this script is located

data_dir = Path('data/')
data_dir_old = data_dir / 'old'
# Read both parquet files
df_nacional = pd.read_parquet(data_dir_old / 'ene_prueba_inicial.parquet')
df_sexo = pd.read_parquet(data_dir_old / 'ene_sexo_prueba_inicial.parquet')
# Process national data (ene_prueba_inicial)
# grupo = "-", valor_grupo = "-", mes from original data
df_nacional_unified = pd.DataFrame({
    'indicador': df_nacional['indicador'],
    'valor_indicador': df_nacional['valor'],
    'grupo': '-',
    'valor_grupo': '-',
    'año': df_nacional['anio'].astype(int),
    'mes': df_nacional['mes'].astype(int).astype(str)  # Keep month as string for consistency
})

# Process sexo data (ene_sexo_prueba_inicial)
# grupo = "sexo", valor_grupo = hombre/mujer, mes = "-" (yearly data)
df_sexo_unified = pd.DataFrame({
    'indicador': df_sexo['indicador'],
    'valor_indicador': df_sexo['valor'],
    'grupo': 'sexo',
    'valor_grupo': df_sexo['sexo'],
    'año': df_sexo['anio'].astype(int),
    'mes': '-'  # Yearly data has no month
})

# Combine both dataframes
df_unified = pd.concat([df_nacional_unified, df_sexo_unified], ignore_index=True)

# Sort by indicador, año, mes, grupo
df_unified = df_unified.sort_values(['indicador', 'año', 'mes', 'grupo', 'valor_grupo']).reset_index(drop=True)

# Save to parquet

df_unified.grupo = df_unified.grupo.replace('-', np.nan)
df_unified.mes = df_unified.mes.replace('-', np.nan)
df_unified['frecuencia'] = np.where(df_unified.mes.isna(), 'anual', 'mensual')

df_unified.to_parquet(data_dir_old / 'ene_unificado.parquet', index=False)


enusc = pd.read_parquet(data_dir_old / 'enusc_unificado.parquet')\
    .drop(columns=['codigo_indicador'])
enusc = enusc[~enusc.grupo.isin(['nse', 'quintil'])]

df_total = pd.concat([df_unified, enusc], ignore_index=True)
df_total.grupo = df_total.grupo.replace('nacional', np.nan)
df_total.valor_grupo = df_total.valor_grupo.replace('Total País', np.nan)
df_total.valor_grupo = df_total.valor_grupo.replace('-', np.nan)
df_total.mes = df_total.mes.astype('Int64', errors='ignore')

output_path = data_dir / 'current/total_unificado.parquet'
df_total.to_parquet(output_path, index=False)

print(f"✅ Unified table saved to: {output_path}")
print(f"\nShape: {df_unified.shape}")
print(f"\nColumns: {df_unified.columns.tolist()}")
print(f"\nFirst 10 rows:")
print(df_unified.head(10))
print(f"\nLast 10 rows:")
print(df_unified.tail(10))
print(f"\nUnique values:")
print(f"  - indicador: {df_unified['indicador'].unique()}")
print(f"  - grupo: {df_unified['grupo'].unique()}")
print(f"  - valor_grupo: {df_unified['valor_grupo'].unique()}")
