"""
app.py
=======
SIMULADOR DE COBERTURA EDUCATIVA — Región Junín (versión web, Streamlit)

Corre localmente con:
    streamlit run app.py

Usa exactamente la misma lógica que simulador.py (importada desde
logica_simulador.py), solo que con controles web en vez de texto en
consola.
"""

import streamlit as st
import pandas as pd

from logica_simulador import (
    preparar_base_fuente1, preparar_base_fuente2,
    filtrar, calcular_indicadores,
    leer_csv_desde_bytes, preparar_base_personalizada,
)

st.set_page_config(
    page_title="Simulador de Cobertura Educativa — Junín 2024",
    layout="wide",
)


# ------------------------------------------------------------------
# Carga de datos (con caché: no se vuelve a leer el CSV en cada clic)
# ------------------------------------------------------------------

@st.cache_data
def cargar_fuente1() -> pd.DataFrame:
    return preparar_base_fuente1()


@st.cache_data
def cargar_fuente2() -> pd.DataFrame:
    return preparar_base_fuente2()


def asistente_dataset_personalizado():
    """
    Muestra el flujo de subir un CSV externo y mapear sus columnas.
    Devuelve (base, etiqueta_zona, criterio_deficit) si el usuario ya
    completó el mapeo correctamente, o None si todavía falta algo.
    """
    st.markdown("**Sube tu archivo CSV**")
    archivo = st.file_uploader("Archivo CSV", type=["csv"], label_visibility="collapsed")

    if archivo is None:
        st.caption(
            "Sube un CSV con datos de matrícula y docentes por zona geográfica "
            "(de cualquier región o año — no tiene que ser de Junín)."
        )
        return None

    try:
        df_crudo, encoding_usado, sep_usado = leer_csv_desde_bytes(archivo.getvalue())
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        return None

    st.success(f"Leído: {len(df_crudo)} filas · separador `{sep_usado}` · codificación `{encoding_usado}`")
    with st.expander("Ver primeras filas del archivo"):
        st.dataframe(df_crudo.head())

    st.markdown("**¿Qué columna corresponde a cada dato?**")
    opciones = ["(ninguna)"] + df_crudo.columns.tolist()

    col_provincia = st.selectbox("Provincia / región", opciones)
    col_distrito = st.selectbox("Distrito / zona", opciones)
    col_estudiantes = st.selectbox("Total de estudiantes", opciones)
    col_docentes = st.selectbox("Total de docentes", opciones)
    col_nivel = st.selectbox("Nivel educativo (opcional)", opciones)
    col_secciones = st.selectbox("N.º de secciones/aulas (opcional)", opciones)

    estandar_docente = 30
    if col_secciones == "(ninguna)":
        estandar_docente = st.number_input(
            "Estándar: estudiantes máx. por docente (para calcular déficit)",
            min_value=1, value=30, step=1,
        )

    obligatorias = [col_provincia, col_distrito, col_estudiantes, col_docentes]
    if "(ninguna)" in obligatorias:
        st.warning("Falta indicar Provincia, Distrito, Estudiantes o Docentes para continuar.")
        return None

    mapeo = {
        "provincia": col_provincia,
        "distrito": col_distrito,
        "total_estudiantes": col_estudiantes,
        "total_docentes": col_docentes,
        "nivel": col_nivel if col_nivel != "(ninguna)" else None,
        "total_secciones": col_secciones if col_secciones != "(ninguna)" else None,
    }

    base, reporte = preparar_base_personalizada(df_crudo, mapeo, estandar_docente)

    if reporte["filas_descartadas"] > 0:
        st.warning(
            f"Se descartaron {reporte['filas_descartadas']} de {reporte['filas_originales']} filas "
            f"por tener estudiantes/docentes vacíos o no numéricos."
        )
    if reporte["filas_utilizadas"] == 0:
        st.error("No quedó ninguna fila utilizable. Revisa el mapeo de columnas.")
        return None

    st.success(f"Base lista: {reporte['filas_utilizadas']} filas utilizables.")
    st.caption(
        " Este archivo lo subiste tú — no forma parte de las fuentes oficiales "
        "de este proyecto (MINEDU/INEI). Se procesa con la misma lógica, pero la "
        "veracidad de los datos es responsabilidad de quien los sube."
    )

    criterio_deficit = (
        "secciones reales registradas" if mapeo["total_secciones"]
        else f"estándar personalizado ({estandar_docente} estudiantes/docente)"
    )
    return base, "Distrito/Zona", criterio_deficit


# ------------------------------------------------------------------
# Encabezado
# ------------------------------------------------------------------

st.title("Simulador de Cobertura Educativa — Junín 2024")
st.caption(
    "Elige una fuente de datos y los filtros en la barra lateral. "
    "Luego simula escenarios de aumento de matrícula o incorporación de docentes."
)

# ------------------------------------------------------------------
# Barra lateral: fuente de datos y filtros
# ------------------------------------------------------------------

with st.sidebar:
    st.header("Filtros")

    fuente_label = st.radio(
        "Fuente de datos",
        options=[
            "EBR pública, con nivel educativo (Datasets 1+2)",
            "Todas las modalidades, con secciones reales (Dataset 3)",
            "Subir mi propio dataset",
        ],
    )

    if fuente_label.startswith("EBR"):
        fuente = "1"
        base = cargar_fuente1()
        etiqueta_distrito = "Distrito"
        criterio_deficit = "estándar MINEDU (estudiantes/aula)"
    elif fuente_label.startswith("Todas"):
        fuente = "2"
        base = cargar_fuente2()
        etiqueta_distrito = "UGEL (agrupación de distritos)"
        criterio_deficit = "secciones reales registradas"
    else:
        fuente = "3"
        resultado = asistente_dataset_personalizado()
        if resultado is None:
            st.stop()
        base, etiqueta_distrito, criterio_deficit = resultado

    provincias = ["(Todas)"] + sorted(base["provincia"].unique())
    provincia_sel = st.selectbox("Provincia", provincias)
    provincia = None if provincia_sel == "(Todas)" else provincia_sel

    if provincia is not None:
        distritos_disponibles = sorted(base[base["provincia"] == provincia]["distrito"].unique())
    else:
        distritos_disponibles = sorted(base["distrito"].unique())

    distritos = ["(Todos)"] + distritos_disponibles
    distrito_sel = st.selectbox(etiqueta_distrito, distritos)
    distrito = None if distrito_sel == "(Todos)" else distrito_sel

    nivel = None
    if "nivel" in base.columns:
        niveles = ["(Todos)"] + sorted(base["nivel"].unique())
        nivel_sel = st.selectbox("Nivel educativo", niveles)
        nivel = None if nivel_sel == "(Todos)" else nivel_sel
    elif fuente == "2":
        st.caption(
            "*El Dataset 3 no permite filtrar por nivel de forma confiable.*"
            "(ver limitación explicada en el informe)."
        )

# ------------------------------------------------------------------
# Referencia regional (para poder interpretar cualquier zona, elegida
# específicamente o en el ranking general, contra el mismo promedio)
# ------------------------------------------------------------------

promedio_regional = calcular_indicadores(base)["estudiantes_por_docente"]


def _clasificar_urgencia(ratio: float) -> tuple[str, str]:
    if ratio > promedio_regional * 1.15:
        return "🔴", "Sobrecarga crítica"
    elif ratio >= promedio_regional * 0.85:
        return "🟡", "Carga moderada"
    else:
        return "🟢", "Sin sobrecarga"


etiqueta_zona = etiqueta_distrito.split(" (")[0]  # sin la aclaración entre paréntesis

ranking_completo = (
    base.groupby(["provincia", "distrito"])
    .apply(lambda g: pd.Series(calcular_indicadores(g)))
    .reset_index()
    .rename(columns={"distrito": etiqueta_zona})
)
ranking_completo["Urgencia"] = ranking_completo["estudiantes_por_docente"].apply(
    lambda r: " ".join(_clasificar_urgencia(r))
)
ranking_completo = ranking_completo.sort_values("estudiantes_por_docente", ascending=False).reset_index(drop=True)
ranking_completo["Posición"] = ranking_completo.index + 1

# ------------------------------------------------------------------
# Filtrado y cálculo de indicadores
# ------------------------------------------------------------------

df_filtrado = filtrar(base, provincia, distrito, nivel)

if len(df_filtrado) == 0:
    st.warning("No hay instituciones que coincidan con esa combinación de filtros.")
    st.stop()

ind = calcular_indicadores(df_filtrado)

partes_titulo = [provincia or "Todas las provincias", distrito or "Todos los distritos"]
if "nivel" in base.columns:
    partes_titulo.append(nivel or "Todos los niveles")
st.subheader(" / ".join(partes_titulo))

# ------------------------------------------------------------------
# Veredicto de la zona elegida (le da sentido real a elegir un filtro
# específico, en vez de solo mostrar números sueltos)
# ------------------------------------------------------------------

emoji, etiqueta_urgencia = _clasificar_urgencia(ind["estudiantes_por_docente"])
diferencia_pct = round((ind["estudiantes_por_docente"] / promedio_regional - 1) * 100, 1)
texto_diferencia = f"{'+' if diferencia_pct >= 0 else ''}{diferencia_pct}%"

mensaje_veredicto = (
    f"**{emoji} {etiqueta_urgencia}** — {ind['estudiantes_por_docente']} estudiantes por docente "
    f"({texto_diferencia} respecto al promedio regional de {promedio_regional})."
)

# Si se eligió una zona puntual sin mezclar niveles, también se puede
# mostrar su posición exacta dentro del ranking regional completo.
if distrito is not None and nivel is None:
    fila_zona = ranking_completo[
        (ranking_completo["provincia"] == provincia) & (ranking_completo[etiqueta_zona] == distrito)
    ]
    if len(fila_zona) == 1:
        posicion = int(fila_zona.iloc[0]["Posición"])
        total_zonas = len(ranking_completo)
        mensaje_veredicto += f" Ocupa el puesto **#{posicion} de {total_zonas}** {etiqueta_zona.lower()}s con mayor urgencia."

if emoji == "🔴":
    st.error(mensaje_veredicto)
elif emoji == "🟡":
    st.warning(mensaje_veredicto)
else:
    st.success(mensaje_veredicto)

# ------------------------------------------------------------------
# Indicadores actuales (tarjetas)
# ------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)
col1.metric("Instituciones educativas", ind["colegios"])
col2.metric("Total estudiantes", f"{ind['total_estudiantes']:,}")
col3.metric("Total docentes", f"{ind['total_docentes']:,}")
col4.metric("Estudiantes por docente", ind["estudiantes_por_docente"])

col5, col6, col7 = st.columns(3)
col5.metric("Estudiantes por institución", ind["estudiantes_por_institucion"])
if "estudiantes_por_seccion" in ind:
    col6.metric("Estudiantes por sección", ind["estudiantes_por_seccion"])

# Si se están mezclando varios niveles educativos, el promedio de arriba puede
# resultar engañoso (los jardines de Inicial suelen ser muy pequeños comparados
# con las secundarias, y eso arrastra el promedio hacia abajo). Se muestra el
# desglose para que no se malinterprete como "todos los colegios son chicos".
if nivel is None and "nivel" in df_filtrado.columns and df_filtrado["nivel"].nunique() > 1:
    st.caption(
        " El promedio de arriba mezcla niveles con tamaños muy distintos "
        "(jardines pequeños junto con secundarias grandes). Desglose real:"
    )
    desglose_nivel = (
        df_filtrado.groupby("nivel")
        .agg(colegios=("nivel", "count"), total_estudiantes=("total_estudiantes", "sum"))
        .reset_index()
    )
    desglose_nivel["promedio_por_colegio"] = round(
        desglose_nivel["total_estudiantes"] / desglose_nivel["colegios"], 2
    )
    st.dataframe(desglose_nivel, hide_index=True, use_container_width=True)

signo = "🔴 Déficit" if ind["deficit_docente"] > 0 else ("🟢 Superávit" if ind["deficit_docente"] < 0 else "🟡 Exacto")
col7.metric(
    f"{signo} docente (vs. {criterio_deficit})",
    abs(ind["deficit_docente"]),
)

st.divider()

# ------------------------------------------------------------------
# 🚨 Ranking de urgencia: ¿dónde se necesitan más docentes?
# ------------------------------------------------------------------
# Se usa "estudiantes por docente" (no el déficit contra el estándar)
# porque el estándar de aula sobreestima el superávit en secundaria
# (ver FAQ). El ranking compara cada zona contra el promedio regional
# de la fuente elegida — un criterio siempre disponible y sin
# supuestos externos.

st.subheader("Ranking de urgencia: ¿dónde se necesitan más docentes?")
st.caption(
    "Pensado para gestores educativos: qué zonas están relativamente más "
    "sobrecargadas de estudiantes por docente, comparadas con el promedio regional."
)

top_n = st.slider("¿Cuántas zonas mostrar?", min_value=5, max_value=30, value=10)
ranking_top = ranking_completo.head(top_n)

st.dataframe(
    ranking_top[["Urgencia", "provincia", etiqueta_zona, "colegios",
                 "total_estudiantes", "total_docentes", "estudiantes_por_docente"]]
    .rename(columns={
        "provincia": "Provincia", "colegios": "Colegios",
        "total_estudiantes": "Estudiantes", "total_docentes": "Docentes",
        "estudiantes_por_docente": "Estudiantes/docente",
    }),
    hide_index=True, use_container_width=True,
)

st.caption(f"Promedio regional de referencia: **{promedio_regional} estudiantes por docente**.")

st.subheader("Comparación entre todas las provincias")

comparacion_provincias = (
    base.groupby("provincia")
    .apply(lambda g: pd.Series(calcular_indicadores(g)))
    .reset_index()
    .sort_values("estudiantes_por_docente", ascending=False)
)

st.bar_chart(
    comparacion_provincias.set_index("provincia")["estudiantes_por_docente"]
)

with st.expander("Ver tabla completa por provincia"):
    st.dataframe(comparacion_provincias, hide_index=True, use_container_width=True)

st.divider()

# ------------------------------------------------------------------
# Preguntas frecuentes (para que cualquier visitante entienda los datos)
# ------------------------------------------------------------------

st.subheader("Preguntas frecuentes")

with st.expander("¿Por qué 'Estudiantes por docente' tiene decimales? ¿No debería ser un número entero?"):
    st.markdown(
        """
        Porque es un **promedio**, no un conteo. Se calcula dividiendo el total de
        estudiantes entre el total de docentes de la zona elegida.

        Por ejemplo, si hay **87,795 estudiantes** y **5,510 docentes**, el resultado es
        `87795 ÷ 5510 = 15.93`.

        Ese `15.93` no significa que exista un docente con "0.93 de un estudiante" —
        significa que, **en promedio**, hay casi 16 estudiantes por cada docente en
        esa zona. Es el mismo tipo de cifra que ves cuando se dice "el promedio de
        hijos por familia es 2.3": describe una tendencia general, no un caso
        individual exacto.
        """
    )

with st.expander("¿Qué significa 'Déficit docente' o 'Superávit docente'?"):
    st.markdown(
        """
        Es la diferencia entre los **docentes que hay actualmente** y los
        **docentes que se necesitarían** según un criterio de referencia:

        - Si usas la fuente **EBR pública**, el criterio es la norma del MINEDU
          sobre el máximo de estudiantes por aula (25 en inicial, 30 en primaria
          y secundaria), asumiendo 1 docente por aula.
        - Si usas la fuente **Todas las modalidades**, el criterio es el número
          real de secciones (aulas) registradas en cada colegio.

        **🔴 Déficit** = faltan docentes según ese criterio.
        **🟢 Superávit** = hay más docentes de los que ese criterio exige.

        Esto es una **estimación con supuestos explícitos**, no una medición
        oficial de necesidad docente — está pensada para comparar zonas entre sí,
        no como cifra exacta de contratación.
        """
    )

with st.expander("¿Cuál es la diferencia entre las fuentes de datos disponibles?"):
    st.markdown(
        """
        | | EBR pública (Datasets 1+2) | Todas las modalidades (Dataset 3) | Mi propio dataset |
        |---|---|---|---|
        | Qué cubre | Solo colegios públicos de Inicial, Primaria y Secundaria | Además incluye Técnico Productiva, Básica Alternativa y Básica Especial | Lo que traiga tu archivo |
        | Filtro por nivel | Sí, disponible | No disponible | Solo si mapeas una columna de nivel |
        | Zona geográfica | Provincia y distrito real | Provincia y UGEL | Las columnas que tú indiques |
        | Base del déficit docente | Norma MINEDU de estudiantes por aula | Número real de secciones registradas | Secciones (si las mapeas) o un estándar que tú defines |

        Ninguna es "mejor" en general — cada una sirve para un tipo de análisis distinto.
        """
    )

with st.expander("¿Cómo funciona la opción de subir mi propio dataset?"):
    st.markdown(
        """
        Puedes subir cualquier archivo CSV que tenga, por columnas separadas:
        una **provincia/región**, una **zona más específica** (distrito, UGEL,
        lo que sea), un **total de estudiantes** y un **total de docentes** por
        fila. La página detecta sola la codificación y el separador del
        archivo, y tú solo indicas qué columna es cuál.

        Opcionalmente puedes mapear también **nivel educativo** (para poder
        filtrar por nivel) y **número de secciones** (para un cálculo de
        déficit docente más preciso). Si no tienes secciones, tú mismo defines
        el estándar de "estudiantes máximo por docente" a usar.

        **Importante:** los datos que subas no forman parte de las fuentes
        oficiales de este proyecto (MINEDU/INEI) — la página los procesa con
        la misma lógica, pero la veracidad de esos datos es responsabilidad
        de quien los sube. Útil, por ejemplo, para analizar otra región, otro
        año, o datos de tu propia institución.
        """
    )

with st.expander("¿Qué es una UGEL?"):
    st.markdown(
        """
        Una **UGEL** (Unidad de Gestión Educativa Local) es la oficina del
        Ministerio de Educación que administra los colegios de una zona
        determinada — parecido a una "sede regional" del sector educación.
        Una UGEL puede abarcar varios distritos, por eso en la fuente
        "Todas las modalidades" vas a ver menos opciones geográficas que
        distritos reales tiene la provincia.
        """
    )

with st.expander("¿Por qué 'Estudiantes por institución' a veces parece un número muy bajo?"):
    st.markdown(
        """
        Porque ese promedio junta colegios muy distintos en tamaño. En Junín, la
        mayoría de instituciones educativas son **jardines de Inicial pequeños**
        (muchos con menos de 20 niños) ubicados en zonas rurales dispersas de
        sierra y selva — esto es normal y esperado en el sistema educativo
        peruano, donde comunidades pequeñas y alejadas tienen su propio jardín o
        primaria con pocos alumnos, en vez de trasladar a los niños lejos.

        Como hay **muchas más** instituciones pequeñas (Inicial) que grandes
        (Secundaria), el promedio general se "jala" hacia abajo, aunque los
        colegios de Secundaria sí tengan cientos de estudiantes cada uno.

        Por eso, cuando eliges "Todos los niveles", la página te muestra además
        un desglose por nivel educativo — ahí se ve la diferencia real: Inicial
        promedia ~30 estudiantes por colegio, mientras que Secundaria promedia
        ~170.
        """
    )

with st.expander("¿Cómo se decide qué zonas tienen 'Sin sobrecarga', 'Carga moderada' o 'Sobrecarga crítica'?"):
    st.markdown(
        """
        Se compara el "estudiantes por docente" de cada zona contra el
        **promedio de toda la región Junín** (con la fuente de datos que
        elegiste):

        - 🔴 **Sobrecarga crítica**: más de 15% por encima del promedio regional
          (cada docente atiende a más estudiantes de lo habitual en la región).
        - 🟡 **Carga moderada**: cerca del promedio regional (± 15%).
        - 🟢 **Sin sobrecarga**: más de 15% por debajo del promedio regional
          (cada docente atiende a menos estudiantes de lo habitual).

        **Importante — esto mide únicamente carga docente, no calidad ni tamaño.**
        "Sin sobrecarga" no significa que el colegio sea grande, próspero, o
        tenga mejor infraestructura — solo significa que sus docentes no están
        saturados de estudiantes. De hecho, es común que zonas rurales pequeñas
        salgan "Sin sobrecarga" precisamente porque tienen pocos estudiantes en
        total, no porque estén especialmente bien atendidas en otros aspectos.

        **¿Por qué no se usa el "déficit docente" para esta clasificación?**
        Porque, como se explica en la pregunta sobre déficit docente, ese
        cálculo usa un estándar (aulas/secciones) que resulta demasiado
        generoso para el nivel Secundaria — con ese criterio, *toda* la
        región sale en superávit, incluso zonas que claramente están más
        sobrecargadas que otras. Comparar contra el promedio regional evita
        depender de ese supuesto y sigue mostrando diferencias reales entre
        zonas.
        """
    )

with st.expander("¿De dónde salen estos datos?"):
    st.markdown(
        """
        Los tres datasets provienen de fuentes públicas oficiales:

        - **Matrícula escolar**: Ministerio de Educación del Perú (MINEDU).
        - **Docentes por colegio**: Ministerio de Educación del Perú (MINEDU).
        - **Reporte por UGEL**: Ministerio de Educación del Perú (MINEDU).

        Son datos agregados por institución educativa — no contienen nombres
        ni información personal de estudiantes o docentes individuales.
        """
    )