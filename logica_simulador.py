"""
logica_simulador.py
=====================
Toda la lógica "pura" del proyecto: cargar datos, limpiarlos, cruzarlos
y calcular indicadores. NO tiene ningún input()/print() de consola ni
nada de Streamlit — así lo puede usar tanto simulador.py (consola)
como app.py (versión web), sin duplicar código ni arriesgarse a que
den resultados distintos.
"""

import math
import pandas as pd
from pathlib import Path

CARPETA = Path(__file__).resolve().parent

# Estándar MINEDU (Fuente 1): estudiantes máximo por aula/docente, según nivel
ESTANDAR_POR_NIVEL = {
    "Inicial - Cuna-Jardín": 25,
    "Inicial - Jardín": 25,
    "Primaria": 30,
    "Secundaria": 30,
}
ESTANDAR_POR_DEFECTO = 30


def preparar_base_fuente1() -> pd.DataFrame:
    """Datasets 1+2 cruzados por cod_mod. EBR pública, con nivel confiable."""
    matricula = pd.read_csv(CARPETA / "Dataset_1.csv")
    docentes = pd.read_csv(CARPETA / "Dataset_2.csv")

    matricula_resumida = (
        matricula
        .groupby("cod_mod", as_index=False)
        .agg(
            nombre_colegio=("Nombre", "first"),
            nivel=("dsc_nivel", "first"),
            total_estudiantes=("TotalEstudiantes", "sum"),
        )
    )

    docentes_prep = docentes[["cod_mod", "prov", "dist", "gestion", "Docentes_total"]].rename(
        columns={"prov": "provincia", "dist": "distrito", "Docentes_total": "total_docentes"}
    )

    base = pd.merge(matricula_resumida, docentes_prep, on="cod_mod", how="inner")

    base["estandar_nivel"] = base["nivel"].map(ESTANDAR_POR_NIVEL).fillna(ESTANDAR_POR_DEFECTO)
    base["docentes_necesarios"] = (base["total_estudiantes"] / base["estandar_nivel"]).apply(math.ceil)

    return base


def preparar_base_fuente2() -> pd.DataFrame:
    """
    Dataset 3 (reporte por UGEL). Solo se usan las filas de colegio
    individual (n_ie == 1) — lo único garantizado sin ambigüedad en
    este archivo, evitando contar dos veces los subtotales.
    """
    df = pd.read_csv(CARPETA / "Dataset_3_prueba_.csv", sep=";", encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={
        "nª _II.EE": "n_ie",
        "total_alumnos": "total_estudiantes",
        "num_docentes": "total_docentes",
        "num_secciones": "total_secciones",
    })

    df["provincia"] = df["provincia"].str.strip()
    df["distrito"] = df["distrito"].str.strip()

    base = df[df["n_ie"] == 1].copy()
    base["docentes_necesarios"] = base["total_secciones"]  # mínimo 1 docente por sección

    columnas = ["provincia", "distrito", "total_estudiantes", "total_docentes",
                "total_secciones", "docentes_necesarios"]
    return base[columnas]


def filtrar(base: pd.DataFrame, provincia, distrito, nivel=None) -> pd.DataFrame:
    df = base.copy()
    if provincia is not None:
        df = df[df["provincia"] == provincia]
    if distrito is not None:
        df = df[df["distrito"] == distrito]
    if nivel is not None and "nivel" in df.columns:
        df = df[df["nivel"] == nivel]
    return df


def calcular_indicadores(df_filtrado: pd.DataFrame) -> dict:
    colegios = len(df_filtrado)
    total_estudiantes = int(df_filtrado["total_estudiantes"].sum())
    total_docentes = int(df_filtrado["total_docentes"].sum())
    docentes_necesarios = int(df_filtrado["docentes_necesarios"].sum())

    resultado = {
        "colegios": colegios,
        "total_estudiantes": total_estudiantes,
        "total_docentes": total_docentes,
        "estudiantes_por_docente": round(total_estudiantes / total_docentes, 2) if total_docentes else None,
        "estudiantes_por_institucion": round(total_estudiantes / colegios, 2) if colegios else None,
        "docentes_necesarios": docentes_necesarios,
        "deficit_docente": docentes_necesarios - total_docentes,
        "estandar_efectivo": (total_estudiantes / docentes_necesarios) if docentes_necesarios else ESTANDAR_POR_DEFECTO,
    }

    if "total_secciones" in df_filtrado.columns:
        total_secciones = int(df_filtrado["total_secciones"].sum())
        resultado["total_secciones"] = total_secciones
        resultado["estudiantes_por_seccion"] = round(total_estudiantes / total_secciones, 2) if total_secciones else None

    return resultado


def simular(ind_base: dict, nuevos_estudiantes: float, nuevos_docentes: float) -> dict:
    """
    Recalcula los indicadores asumiendo un nuevo total de estudiantes y
    docentes (usa el 'estandar_efectivo' ya calculado en ind_base, que
    representa el ratio ideal de la selección actual).
    """
    nuevos_estudiantes = round(nuevos_estudiantes)
    nuevos_docentes = round(nuevos_docentes)

    docentes_necesarios_sim = math.ceil(nuevos_estudiantes / ind_base["estandar_efectivo"])

    return {
        "total_estudiantes": nuevos_estudiantes,
        "total_docentes": nuevos_docentes,
        "estudiantes_por_docente": round(nuevos_estudiantes / nuevos_docentes, 2) if nuevos_docentes else None,
        "estudiantes_por_institucion": round(nuevos_estudiantes / ind_base["colegios"], 2) if ind_base["colegios"] else None,
        "docentes_necesarios": docentes_necesarios_sim,
        "deficit_docente": docentes_necesarios_sim - nuevos_docentes,
    }


# ------------------------------------------------------------------
# Datasets externos (subidos por cualquier visitante de la app web)
# ------------------------------------------------------------------

def leer_csv_desde_bytes(contenido: bytes):
    """
    Intenta leer un CSV probando codificaciones y separadores comunes,
    sin pedirle nada al usuario primero. Devuelve (DataFrame, encoding, separador).
    Lanza ValueError si no logra decodificarlo con ninguna codificación común.
    """
    from io import StringIO

    texto = None
    encoding_usado = None
    for encoding in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            texto = contenido.decode(encoding)
            encoding_usado = encoding
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError("No se pudo leer el archivo (codificación no reconocida).")

    mejor_df = None
    mejor_sep = None
    for sep in [",", ";", "\t", "|"]:
        try:
            df_prueba = pd.read_csv(StringIO(texto), sep=sep)
        except Exception:
            continue
        if df_prueba.shape[1] > 1 and (mejor_df is None or df_prueba.shape[1] > mejor_df.shape[1]):
            mejor_df, mejor_sep = df_prueba, sep

    if mejor_df is None:
        mejor_df = pd.read_csv(StringIO(texto), sep=None, engine="python")
        mejor_sep = "(detectado automáticamente)"

    return mejor_df, encoding_usado, mejor_sep


def preparar_base_personalizada(df: pd.DataFrame, mapeo: dict, estandar_docente: float):
    """
    Construye una base compatible con el resto del programa a partir de
    un archivo externo, según el mapeo de columnas que indicó el usuario.

    mapeo: dict con claves 'provincia', 'distrito', 'total_estudiantes',
           'total_docentes' (obligatorias) y 'nivel', 'total_secciones'
           (opcionales, pueden ser None), cuyos valores son los nombres
           de columna reales en df.

    Devuelve (base, reporte) — reporte incluye cuántas filas se
    descartaron por tener datos no numéricos, para avisarle al usuario.
    """
    columnas_nuevas = {}
    for clave in ["provincia", "distrito", "total_estudiantes", "total_docentes", "nivel", "total_secciones"]:
        col_origen = mapeo.get(clave)
        if col_origen:
            columnas_nuevas[clave] = df[col_origen].values

    base = pd.DataFrame(columnas_nuevas)
    filas_originales = len(base)

    for col_num in ["total_estudiantes", "total_docentes", "total_secciones"]:
        if col_num in base.columns:
            base[col_num] = pd.to_numeric(base[col_num], errors="coerce")

    base["provincia"] = base["provincia"].astype(str).str.strip()
    base["distrito"] = base["distrito"].astype(str).str.strip()
    if "nivel" in base.columns:
        base["nivel"] = base["nivel"].astype(str).str.strip()

    filas_invalidas = base[["total_estudiantes", "total_docentes"]].isna().any(axis=1).sum()
    base = base.dropna(subset=["total_estudiantes", "total_docentes"]).reset_index(drop=True)

    if "total_secciones" in base.columns:
        base["docentes_necesarios"] = base["total_secciones"].fillna(0).apply(math.ceil)
    else:
        base["docentes_necesarios"] = (base["total_estudiantes"] / estandar_docente).apply(math.ceil)

    reporte = {
        "filas_originales": filas_originales,
        "filas_descartadas": int(filas_invalidas),
        "filas_utilizadas": len(base),
    }
    return base, reporte
