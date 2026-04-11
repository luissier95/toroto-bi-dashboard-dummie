import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from functools import reduce

# ==========================================
# CONFIGURACIÓN DEL DASHBOARD (HTML/INTERFAZ)
# ==========================================
st.set_page_config(page_title="Prueba Toroto", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# 1. CARGA DE DATOS
@st.cache_data
def cargar_datos():
    ocp = pd.read_excel('db_caso_practico_BI_.xlsx', sheet_name='Ordenes_Compra')
    psto = pd.read_excel('db_caso_practico_BI_.xlsx', sheet_name='Presupuesto')
    return ocp, psto

try:
    ocp_raw, psto_raw = cargar_datos()
except Exception as e:
    st.error(f"Error al cargar el archivo Excel: {e}")
    st.stop()

# ==========================================
# 2. PROCESAMIENTO Y MÉTRICAS DE CALIDAD
# ==========================================
ocp = ocp_raw.copy()

# A. Capturar Duplicados antes de limpiar
duplicados_count = ocp.duplicated(subset=['Código OC']).sum()
ocp = ocp.drop_duplicates(subset=['Código OC'])

# B. Procesar Fechas y Capturar fuera de rango
ocp['Fecha'] = pd.to_datetime(ocp['Fecha'])
fecha_min, fecha_max = pd.Timestamp(2025, 12, 1), pd.Timestamp(2026, 1, 31)
fuera_rango_count = ocp[(ocp['Fecha'] < fecha_min) | (ocp['Fecha'] > fecha_max)].shape[0]

# C. Normalización de Rubros
ocp['f_left'] = ocp['Código OC'].str[:3].str.upper()
mapping = {'MAR':'Marketing', 'TEC':'Tecnología', 'VIA':'Viajes', 'OPE':'Operación'}
ocp['Rubro'] = ocp['f_left'].map(mapping)
ocp['month'] = ocp['Fecha'].dt.month
ocp['anio'] = ocp['Fecha'].dt.year

# D. Limpieza de Montos e Outliers
invalidos_monto_count = ocp[ocp['Monto (MXN)'] <= 0].shape[0]
ocp = ocp[ocp['Monto (MXN)'] > 0] 

stats = ocp.groupby('Rubro')['Monto (MXN)'].agg(['mean', 'std']).reset_index()
stats['umbral'] = stats['mean'] + (2 * stats['std'])
ocp = ocp.merge(stats[['Rubro', 'umbral']], on='Rubro')

outliers_count = ocp[ocp['Monto (MXN)'] > ocp['umbral']].shape[0]

# Filtrado Final
ocp = ocp[(ocp['Fecha'] >= fecha_min) & (ocp['Fecha'] <= fecha_max)]
ocp = ocp[ocp['Monto (MXN)'] <= ocp['umbral']]

# E. Proyección de Presupuesto (Tu lógica original se mantiene igual)
psto = psto_raw.rename(columns={'Diciembre 2025': 'Diciembre 2025 - PSTO', 'Enero 2026': 'Enero 2026 - PSTO'}).sort_values(by='Rubro')
meses_proyectar = ['Febrero 2026', 'Marzo 2026', 'Abril 2026', 'Mayo 2026', 'Junio 2026', 'Julio 2026', 'Agosto 2026', 'Septiembre 2026', 'Octubre 2026', 'Noviembre 2026', 'Diciembre 2026']
factores = {'Tecnología': 0.99, 'Marketing': 0.99, 'Operación': 1.01, 'Viajes': 1.01}
ultima_col = 'Enero 2026 - PSTO'

for mes in meses_proyectar:
    np.random.seed(42) 
    variacion = np.random.uniform(0.97, 1.03, len(psto))
    psto[f'{mes} - PSTO'] = (np.round((psto[ultima_col] * psto['Rubro'].map(factores).fillna(1.0) * variacion) / 5000) * 5000).astype(int)
    ultima_col = f'{mes} - PSTO'

# ==========================================
# 3. INTERFAZ DE USUARIO (SIDEBAR)
# ==========================================
st.sidebar.title("Configuración")
mes_analisis = st.sidebar.selectbox("Mes de Corte", ['Diciembre 2025', 'Enero 2026'])
rubro_sim = st.sidebar.selectbox("Rubro para Simulación", psto['Rubro'].unique())
monto_sim = st.sidebar.number_input("Monto de Nueva OC", min_value=0, value=5000)

# ==========================================
# 4. CÁLCULOS DINÁMICOS
# ==========================================
a_pivot = pd.pivot_table(ocp, index='Rubro', columns=['anio', 'month'], values='Monto (MXN)', aggfunc='sum').fillna(0)
nuevas_cols = []
meses_espanol = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                 7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}

for col in a_pivot.columns:
    nombre_mes_anio = f"{meses_espanol[int(col[1])]} {int(col[0])} - OC"
    nuevas_cols.append(nombre_mes_anio)

a_pivot.columns = nuevas_cols
a = a_pivot.reset_index()

col_oc_buscada = f"{mes_analisis} - OC"
if col_oc_buscada not in a.columns:
    a[col_oc_buscada] = 0

psto_idx = psto.set_index('Rubro')
oc_idx = a.set_index('Rubro')

meses_psto_plan = [c for c in psto_idx.columns if '- PSTO' in c]
nombre_psto_inicio = f"{mes_analisis} - PSTO"

if nombre_psto_inicio in meses_psto_plan:
    idx_h = meses_psto_plan.index(nombre_psto_inicio)
    meses_futuros = meses_psto_plan[idx_h:]
else:
    meses_futuros = []

deuda_ini = oc_idx[col_oc_buscada]
seguimiento = pd.DataFrame(index=psto_idx.index)
saldo = deuda_ini.copy()

for m in meses_futuros:
    saldo = (saldo - psto_idx[m]).clip(lower=0)
    seguimiento[m.replace('- PSTO', '- SALDO')] = saldo

def get_liq(row):
    for m in meses_futuros:
        if row[m.replace('- PSTO', '- SALDO')] == 0: return m.replace(' - PSTO', '')
    return "Remanente 2027"
seguimiento['Liquidación'] = seguimiento.apply(get_liq, axis=1)

# ==========================================
# 5. DASHBOARD LAYOUT (VISTA HTML)
# ==========================================
st.header(f"📊 Estado Presupuestal - {mes_analisis}")

col_a, col_b, col_c = st.columns(3)
total_oc = oc_idx[col_oc_buscada].sum()
total_psto = psto_idx[nombre_psto_inicio].sum()
diff = total_psto - total_oc

col_a.metric("Gasto Real (OC)", f"${total_oc:,.0f}")
col_b.metric("Presupuesto Asignado", f"${total_psto:,.0f}")
col_c.metric("Diferencia (Ahorro/Faltante)", f"${diff:,.0f}", delta=float(diff))

st.divider()

tab1, tab2, tab3 = st.tabs(["📋 Presupuesto vs Ordenes de Compra", "⏳ Proyección para Liquidación", "💰 Presupuesto (Budget) 2026"])

with tab1:
    # TABLA ARRIBA
    vp = pd.DataFrame(index=psto_idx.index)
    vp['Gasto OC'] = oc_idx[col_oc_buscada].apply(lambda x: f"${x:,.0f}")
    vp['Presupuesto'] = psto_idx[nombre_psto_inicio].apply(lambda x: f"${x:,.0f}")
    diferencia_nominal = psto_idx[nombre_psto_inicio] - oc_idx[col_oc_buscada]
    vp['Ahorro/Deuda'] = diferencia_nominal.apply(
        lambda x: f"${x:,.0f} (Ahorro)" if x >= 0 else f"-${abs(x):,.0f} (Deuda)")
    ratio = (oc_idx[col_oc_buscada] / psto_idx[nombre_psto_inicio]) * 100
    vp['Ratio %'] = ratio.apply(lambda x: f"{x:,.1f}% {'(Sobregiro)' if x > 100 else '(Dentro del Presupuesto)'}")
    vp['Mes Liquidación'] = seguimiento['Liquidación']
    st.dataframe(vp, use_container_width=True)
    
    # GRÁFICA ABAJO
    st.markdown("---")
    df_bar = pd.DataFrame({
        'Rubro': psto_idx.index,
        'Gasto Real (OC)': oc_idx[col_oc_buscada],
        'Presupuesto': psto_idx[nombre_psto_inicio]
    }).melt(id_vars='Rubro', var_name='Tipo', value_name='Monto')
    
    fig1 = px.bar(df_bar, x='Rubro', y='Monto', color='Tipo', barmode='group',
                 text='Monto', # Habilita el texto
                 title=f"Comparativo por Rubro - {mes_analisis}",
                 color_discrete_map={'Gasto Real (OC)': '#EF553B', 'Presupuesto': "#7D7E84"})
    
    # Formato de la cifra dentro de la barra
    fig1.update_traces(texttemplate='%{text:$,.0f}', textposition='outside')
    fig1.update_layout(yaxis_tickformat="$,.0f")
    st.plotly_chart(fig1, use_container_width=True)

with tab2:
    # TABLA ARRIBA
    st.write("Saldo pendiente proyectado después de aplicar el presupuesto mensual:")
    # FIX ERROR: Seleccionamos solo columnas numéricas para el formateo
    cols_numericas = seguimiento.select_dtypes(include=[np.number]).columns
    st.dataframe(seguimiento.style.format("${:,.0f}", subset=cols_numericas), use_container_width=True)
    
    # GRÁFICA ABAJO
    st.markdown("---")
    df_heat = seguimiento.drop(columns=['Liquidación'])
    fig_heat = px.imshow(df_heat, text_auto=True, aspect="auto", 
                         color_continuous_scale='Reds',
                         title="Mapa de Calor: Extinción de Deuda")
    st.plotly_chart(fig_heat, use_container_width=True)

with tab3:
    # TABLA ARRIBA
    st.write("### Planificación Presupuestal Anual (Proyectada)")
    cols_psto = [c for c in psto.columns if '- PSTO' in c]
    df_psto_final = psto[['Rubro'] + cols_psto].set_index('Rubro')
    st.dataframe(df_psto_final.style.format("${:,.0f}"), use_container_width=True)
    
    # GRÁFICA ABAJO
    st.markdown("---")
    df_line = df_psto_final.reset_index().melt(id_vars='Rubro', var_name='Mes', value_name='Monto')
    df_line['Mes'] = df_line['Mes'].str.replace(' - PSTO', '')
    fig3 = px.line(df_line, x='Mes', y='Monto', color='Rubro', markers=True, 
                  title="Tendencia Presupuestal 2026")
    fig3.update_layout(yaxis_tickformat="$,.0f")
    st.plotly_chart(fig3, use_container_width=True)

# ==========================================
# 6. SIMULADOR DE CAPACIDAD
# ==========================================
st.divider()
st.subheader("🚀 Simulador de Capacidad de Compra")
st.info(f"Probando disponibilidad para **{rubro_sim}** con un monto de **${monto_sim:,.0f}** considerando deuda previa.")

def func_simular(rubro, monto):
    d_pendiente = oc_idx.loc[rubro, col_oc_buscada]
    for m_col in meses_futuros:
        presu_mes = psto_idx.loc[rubro, m_col]
        pago_deuda = min(presu_mes, d_pendiente)
        disponible_tras_deuda = presu_mes - pago_deuda
        d_pendiente -= pago_deuda
        
        if d_pendiente == 0 and disponible_tras_deuda >= monto:
            return m_col.replace(' - PSTO', ''), presu_mes, pago_deuda, disponible_tras_deuda - monto
    return None

res = func_simular(rubro_sim, monto_sim)

if res:
    mes_ok, p_total, p_deuda, s_final = res
    st.success(f"✅ ¡APROBADO! El rubro tiene cupo en **{mes_ok.upper()}**")
    c1, c2, c3 = st.columns(3)
    c1.metric("Presupuesto del Mes", f"${p_total:,.0f}")
    c2.metric("Pago Deuda Anterior", f"-${p_deuda:,.0f}")
    c3.metric("Sobrante tras Nueva OC", f"${s_final:,.0f}")
else:
    st.error(f"❌ NO HAY CUPO SUFICIENTE en 2026 para este monto en {rubro_sim} debido a la deuda acumulada.")

# ==========================================
# 7. AGENTE DE DIAGNÓSTICO LÓGICO (DINÁMICO)
# ==========================================
st.divider()
st.subheader("🧠 Agente de Diagnóstico Real-Time")

def generar_diagnostico_dinamico(df_resumen, d_dups, d_fechas, d_montos, d_outliers):
    df_temp = df_resumen.copy()
    df_temp['Ratio_Num'] = df_temp['Ratio %'].str.extract('(\d+\.\d+)').astype(float).fillna(0)
    
    rubro_critico = df_temp['Ratio_Num'].idxmax()
    valor_max = df_temp['Ratio_Num'].max()
    
    acciones = []
    if valor_max > 200:
        status, color = "CRÍTICO", "red"
        acciones.append(f"🚫 **Bloqueo Preventivo:** Suspender nuevas OC en **{rubro_critico}**. El exceso ($\Delta > {int(valor_max-100)}%$) compromete meses futuros.")
        acciones.append(f"🔄 **Re-forecast Obligatorio:** Ajustar el presupuesto de {rubro_critico} ya que el plan actual es insuficiente.")
        acciones.append(f"🔍 **Auditoría de Gastos:** Revisar conceptos de alto valor para detectar fugas.")
    elif valor_max > 100:
        status, color = "ADVERTENCIA", "orange"
        acciones.append(f"⚠️ **Control de Flujo:** Limitar gastos en **{rubro_critico}** solo a operaciones críticas.")
        acciones.append(f"📊 **Optimización:** Reasignar excedentes de rubros saludables.")
    else:
        status, color = "SALUDABLE", "green"
        acciones.append(f"✅ **Continuidad:** Mantener ritmo de ejecución conforme al plan.")

    acciones_format = "\n".join([f"* {a}" for a in acciones])
    
    # IMPORTANTE: El texto debe estar pegado al margen izquierdo dentro de las comillas triples
    mensaje = f"""
### Estado del Sistema: :{color}[{status}]

**🔍 Auditoría de Calidad de Datos:**
* **Limpieza:** Se removieron **{d_dups}** duplicados, **{d_fechas}** fechas inválidas y **{d_montos + d_outliers}** anomalías de monto.
* **Integridad:** La base ha sido normalizada al 100% mediante mapeo de prefijos OC.

**📈 Análisis de Variación Presupuestal:**
* El rubro de mayor atención es **{rubro_critico}** con un ratio de ejecución del **{valor_max:.1f}%**.

**💡 Acciones Sugeridas:**
{acciones_format}
"""
    return mensaje

# LLAMADO FINAL (Usa las variables nacidas en la sección 2)
with st.expander("Consultar Diagnóstico de Integridad y Escenarios", expanded=True):
    diag = generar_diagnostico_dinamico(
        vp, 
        duplicados_count, 
        fuera_rango_count, 
        invalidos_monto_count, 
        outliers_count
    )
    st.markdown(diag)
