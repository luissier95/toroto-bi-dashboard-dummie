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
    ocp = pd.read_excel('db_caso_practico_BI_dummie.xlsx', sheet_name='Ordenes_Compra')
    psto = pd.read_excel('db_caso_practico_BI_dummie.xlsx', sheet_name='Presupuesto')
    return ocp, psto

try:
    ocp_raw, psto_raw = cargar_datos()
except Exception as e:
    st.error(f"Error al cargar el archivo Excel: {e}")
    st.stop()

# ==========================================
# 2. PROCESAMIENTO Y PROYECCIÓN
# ==========================================
ocp = ocp_raw.copy()
ocp['Código OC'] = ocp['Código OC'].str.upper().drop_duplicates()
ocp['Fecha'] = pd.to_datetime(ocp['Fecha'])
ocp['month'] = ocp['Fecha'].dt.month
ocp['anio'] = ocp['Fecha'].dt.year
ocp['f_left'] = ocp['Código OC'].str[:3].str.upper()
mapping = {'MAR':'Marketing', 'TEC':'Tecnología', 'VIA':'Viajes', 'OPE':'Operación'}
ocp['Rubro'] = ocp['f_left'].map(mapping)

stats = ocp.groupby('Rubro')['Monto (MXN)'].agg(['mean', 'std']).reset_index()
stats['umbral'] = stats['mean'] + (2 * stats['std'])
ocp = ocp.merge(stats[['Rubro', 'umbral']], on='Rubro')
ocp = ocp[(ocp['Monto (MXN)'] > 0) & (ocp['Monto (MXN)'] <= ocp['umbral'])]

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
