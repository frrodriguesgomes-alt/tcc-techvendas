"""
app.py — TCC: Data Analytics para Inteligência de Negócios
Empresa: TechVendas Solutions
"""

import os
import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from groq import Groq
from dotenv import load_dotenv

from database import carregar_vendas, carregar_itens, carregar_inadimplencia

load_dotenv()

# ─────────────────────────────────────────────
# HELPERS — Formatação padrão brasileiro
# ─────────────────────────────────────────────
def brl(valor: float) -> str:
    """R$ 1.234,56"""
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def pct(valor: float, casas: int = 1) -> str:
    """12,3%"""
    return f"{valor:.{casas}f}%".replace(".", ",")

def inteiro(valor) -> str:
    """1.234"""
    return f"{int(valor):,}".replace(",", ".")

SEPARATORS = ",."   # decimal=vírgula, milhar=ponto nos gráficos Plotly

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="TechVendas — Dashboard Executivo",
    page_icon="📊",
    layout="wide",
)

st.title("📊 TechVendas Solutions — Dashboard Executivo")
st.caption("Trabalho de Conclusão de Curso · Formação Data Analytics · Digital College")

# ─────────────────────────────────────────────
# ETAPA A — CARREGAMENTO DOS DADOS (com cache)
# ─────────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner="Conectando ao banco de dados...")
def load_all_data():
    df_vendas = carregar_vendas()
    df_itens  = carregar_itens()
    df_inadim = carregar_inadimplencia()
    return df_vendas, df_itens, df_inadim

df_vendas, df_itens, df_inadim = load_all_data()

# ─────────────────────────────────────────────
# ETAPA B — TRATAMENTO E FEATURE ENGINEERING
# ─────────────────────────────────────────────

# --- Vendas ---
df_vendas["data_venda"] = pd.to_datetime(df_vendas["data_venda"], utc=True).dt.tz_convert(None)
df_vendas = df_vendas.rename(columns={"valor": "valor_venda"})
df_vendas["vendedor"] = df_vendas["vendedor"].fillna("Sem Vendedor")
df_vendas["cliente"] = df_vendas["cliente"].fillna("Cliente Não Identificado")
df_vendas["uf"] = df_vendas["uf"].fillna("Não Informado")
df_vendas["forma_pagamento"] = df_vendas["forma_pagamento"].fillna("Não Informado")

df_vendas["data_venda_date"] = df_vendas["data_venda"].dt.date
df_vendas["ano"]             = df_vendas["data_venda"].dt.year
df_vendas["mes"]             = df_vendas["data_venda"].dt.month
df_vendas["mes_ano"]         = df_vendas["data_venda"].dt.to_period("M").astype(str)
df_vendas["trimestre"]       = df_vendas["data_venda"].dt.to_period("Q").astype(str)
df_vendas["comissao"]        = df_vendas["valor_venda"] * 0.025

# --- Itens ---
df_itens["data_venda"] = pd.to_datetime(df_itens["data_venda"], utc=True).dt.tz_convert(None)
df_itens["categoria"] = df_itens["categoria"].fillna("Sem Categoria")
df_itens["custo"] = df_itens["custo"].fillna(0)
df_itens["margem_unitaria"] = df_itens["margem_unitaria"].fillna(0)
df_itens["margem_total"] = df_itens["margem_total"].fillna(0)
df_itens["data_venda_date"] = df_itens["data_venda"].dt.date

# --- Inadimplência (dados pré-agregados por mês/UF/situação no SQL) ---
# data_venda = primeiro dia do mês (DATE_TRUNC no SQL), sem timezone
df_inadim["data_venda"] = pd.to_datetime(df_inadim["data_venda"])
df_inadim["uf"] = df_inadim["uf"].fillna("Não Informado")
df_inadim["data_venda_date"] = df_inadim["data_venda"].dt.date

# 'vencido' já vem calculado no SQL como (vencimento < CURRENT_DATE)
# Inadimplente = ATRASADA  OU  (EM_ABERTO + já vencido)
HOJE = pd.Timestamp(datetime.date.today())

df_inadim["inadimplente"] = (
    (df_inadim["situacao"] == "ATRASADA")
    | (
        (df_inadim["situacao"] == "EM_ABERTO")
        & (df_inadim["vencido"] == True)
    )
)
# "CANCELADA" não é dívida válida: não entra no denominador da taxa
df_inadim["cancelada"] = df_inadim["situacao"] == "CANCELADA"

# ─────────────────────────────────────────────
# SIDEBAR — FILTROS
# ─────────────────────────────────────────────
st.sidebar.header("🔍 Filtros")

# Intervalo de datas
min_date = df_vendas["data_venda_date"].min()
max_date = df_vendas["data_venda_date"].max()
data_range = st.sidebar.date_input(
    "Período de Vendas",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)
# Suporte para seleção parcial (apenas 1 data escolhida)
if isinstance(data_range, (list, tuple)) and len(data_range) == 2:
    data_ini, data_fim = data_range
else:
    data_ini = data_fim = data_range[0] if isinstance(data_range, (list, tuple)) else data_range

st.sidebar.divider()

# UF do cliente
ufs_disponiveis = sorted([u for u in df_vendas["uf"].unique() if u != "Não Informado"])
uf_sel = st.sidebar.multiselect("🗺️ UF do Cliente", ufs_disponiveis)

# Forma de pagamento
formas_disponiveis = sorted([f for f in df_vendas["forma_pagamento"].unique() if f != "Não Informado"])
forma_sel = st.sidebar.multiselect("💳 Forma de Pagamento", formas_disponiveis)

# Tipo de cliente
tipo_sel = st.sidebar.multiselect("👤 Tipo de Cliente", ["Pessoa Física", "Pessoa Jurídica"])

# Categoria de produto
categorias_disponiveis = sorted(df_itens["categoria"].unique())
cat_sel = st.sidebar.multiselect("📦 Categoria de Produto", categorias_disponiveis)

# Vendedor
vendedores_disponiveis = sorted(df_vendas["vendedor"].unique())
vend_sel = st.sidebar.selectbox("🏆 Vendedor", ["Todos"] + vendedores_disponiveis)

# ─────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────
df_v = df_vendas[
    (df_vendas["data_venda_date"] >= data_ini) &
    (df_vendas["data_venda_date"] <= data_fim)
].copy()

df_i = df_itens[
    (df_itens["data_venda_date"] >= data_ini) &
    (df_itens["data_venda_date"] <= data_fim)
].copy()

df_n = df_inadim[
    (df_inadim["data_venda_date"] >= data_ini) &
    (df_inadim["data_venda_date"] <= data_fim)
].copy()

if uf_sel:
    df_v = df_v[df_v["uf"].isin(uf_sel)]
    df_n = df_n[df_n["uf"].isin(uf_sel)]

if forma_sel:
    df_v = df_v[df_v["forma_pagamento"].isin(forma_sel)]

if tipo_sel:
    df_v = df_v[df_v["tipo_cliente"].isin(tipo_sel)]

if cat_sel:
    df_i = df_i[df_i["categoria"].isin(cat_sel)]

if vend_sel != "Todos":
    df_v = df_v[df_v["vendedor"] == vend_sel]

# ─────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────
total_vendido  = df_v["valor_venda"].sum()
ticket_medio   = df_v["valor_venda"].mean() if len(df_v) > 0 else 0
num_clientes   = df_v["cliente"].nunique()

# Exclui CANCELADA do cálculo: não é dívida válida
df_n_valido    = df_n[~df_n["cancelada"]]
total_inadim   = df_n_valido[df_n_valido["inadimplente"]]["valor_parcela"].sum()
total_parcelas = df_n_valido["valor_parcela"].sum()
taxa_inadim    = (total_inadim / total_parcelas * 100) if total_parcelas > 0 else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("💰 Total Vendido",      brl(total_vendido))
col2.metric("🎯 Ticket Médio",       brl(ticket_medio))
col3.metric("👥 Clientes Únicos",    inteiro(num_clientes))
col4.metric("⚠️ Total Inadimplente", brl(total_inadim))
col5.metric("📉 Taxa Inadimpl.",     pct(taxa_inadim))

st.divider()

# ─────────────────────────────────────────────
# ABAS
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📈 1. Receita",
    "🏆 2. Vendedores",
    "👑 3. Melhores Clientes",
    "📦 4. Produtos",
    "🗺️ 5. Risco Financeiro",
    "💳 6. Formas de Pagamento",
    "🤖 Análise IA (Groq)",
])

# ══════════════════════════════════════════════
# TAB 1 — Receita: gráficos gerenciais com insights claros
# ══════════════════════════════════════════════
with tab1:
    st.subheader("📈 Análise de Receita")
    st.markdown(
        "**Perguntas respondidas:** Qual a evolução das vendas? Onde estão concentradas "
        "geograficamente? Existe sazonalidade ou crescimento consistente?"
    )

    # ── Gráfico 1: Faturamento Anual + Crescimento YoY ──
    rec_ano = (
        df_v.groupby("ano")["valor_venda"]
        .sum()
        .reset_index()
        .sort_values("ano")
    )
    rec_ano["crescimento_pct"] = rec_ano["valor_venda"].pct_change() * 100

    fig_anual = go.Figure()
    fig_anual.add_bar(
        x=rec_ano["ano"].astype(str),
        y=rec_ano["valor_venda"],
        name="Faturamento",
        marker_color="#6C63FF",
        text=rec_ano["valor_venda"],
        texttemplate="R$ %{text:,.0f}",
        textposition="outside",
    )
    fig_anual.add_scatter(
        x=rec_ano["ano"].astype(str),
        y=rec_ano["crescimento_pct"],
        name="Crescimento % a.a.",
        yaxis="y2",
        mode="lines+markers+text",
        line=dict(color="#FF6584", width=2),
        marker=dict(size=8),
        text=rec_ano["crescimento_pct"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else ""),
        textposition="top center",
    )
    fig_anual.update_layout(
        title="Faturamento Anual e Crescimento Ano a Ano",
        yaxis=dict(title="Receita (R$)", tickprefix="R$ "),
        yaxis2=dict(title="Crescimento (%)", overlaying="y", side="right", ticksuffix="%", zeroline=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        separators=SEPARATORS,
        bargap=0.3,
    )
    st.plotly_chart(fig_anual, width="stretch")

    # ── Gráfico 2 + 3: Top Estados e MoM% lado a lado ──
    col_a, col_b = st.columns(2)

    with col_a:
        # Receita por Estado (UF) — insight geográfico
        rec_uf = (
            df_v[df_v["uf"] != "Não Informado"]
            .groupby("uf")["valor_venda"]
            .sum()
            .reset_index()
            .sort_values("valor_venda", ascending=True)
            .tail(15)
        )
        fig_uf_rec = px.bar(
            rec_uf,
            x="valor_venda", y="uf",
            orientation="h",
            text="valor_venda",
            title="Top 15 Estados por Receita",
            color="valor_venda",
            color_continuous_scale="Blues",
            labels={"uf": "", "valor_venda": "Receita (R$)"},
        )
        fig_uf_rec.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
        fig_uf_rec.update_layout(
            separators=SEPARATORS,
            xaxis_tickprefix="R$ ",
            coloraxis_showscale=False,
            margin=dict(l=5),
        )
        st.plotly_chart(fig_uf_rec, width="stretch")

    with col_b:
        # Crescimento Mês a Mês (%) — identifica tendências e sazonalidade
        rec_mes = (
            df_v.groupby("mes_ano")["valor_venda"]
            .sum()
            .reset_index()
            .sort_values("mes_ano")
        )
        rec_mes["mom_pct"] = rec_mes["valor_venda"].pct_change() * 100
        rec_mes = rec_mes.dropna(subset=["mom_pct"]).tail(36)   # últimos 36 meses
        rec_mes["cor"] = rec_mes["mom_pct"].apply(lambda x: "#2E8B57" if x >= 0 else "#DC143C")

        fig_mom = px.bar(
            rec_mes,
            x="mes_ano", y="mom_pct",
            text="mom_pct",
            title="Variação Mês a Mês — Últimos 36 Meses (%)",
            color="cor",
            color_discrete_map="identity",
            labels={"mes_ano": "", "mom_pct": "Variação (%)"},
        )
        fig_mom.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_mom.add_hline(y=0, line_dash="dot", line_color="gray")
        fig_mom.update_layout(separators=SEPARATORS, showlegend=False, xaxis_tickangle=-45)
        st.plotly_chart(fig_mom, width="stretch")

    # ── Gráfico 4: Receita Trimestral PF vs PJ ──
    rec_tipo = (
        df_v.groupby(["trimestre", "tipo_cliente"])["valor_venda"]
        .sum()
        .reset_index()
        .sort_values("trimestre")
    )
    fig_pf_pj = px.area(
        rec_tipo,
        x="trimestre", y="valor_venda",
        color="tipo_cliente",
        title="Receita Trimestral: Pessoa Física vs Jurídica",
        labels={"trimestre": "Trimestre", "valor_venda": "Receita (R$)", "tipo_cliente": "Perfil"},
        color_discrete_map={"Pessoa Física": "#6C63FF", "Pessoa Jurídica": "#FF6584"},
    )
    fig_pf_pj.update_layout(separators=SEPARATORS, yaxis_tickprefix="R$ ", xaxis_tickangle=-45)
    st.plotly_chart(fig_pf_pj, width="stretch")

    with st.expander("Ver receita mensal detalhada"):
        tbl_mensal = (
            df_v.groupby("mes_ano")["valor_venda"]
            .sum()
            .reset_index()
            .sort_values("mes_ano", ascending=False)
        )
        tbl_mensal["valor_venda"] = tbl_mensal["valor_venda"].apply(brl)
        tbl_mensal.columns = ["Mês/Ano", "Total Vendido"]
        st.dataframe(tbl_mensal, width="stretch", hide_index=True)

# ══════════════════════════════════════════════
# TAB 2 — Vendedores: Top 5 + Abaixo da Média
# ══════════════════════════════════════════════
with tab2:
    st.subheader("🏆 Performance de Vendedores")
    st.markdown("**Perguntas:** Quem são os top 5 vendedores? Quem está abaixo da média?")

    # Usar todos os vendedores (sem filtro de vendedor individual) para comparação
    df_v_todos = df_vendas[
        (df_vendas["data_venda_date"] >= data_ini) &
        (df_vendas["data_venda_date"] <= data_fim)
    ].copy()
    if uf_sel:
        df_v_todos = df_v_todos[df_v_todos["uf"].isin(uf_sel)]
    if forma_sel:
        df_v_todos = df_v_todos[df_v_todos["forma_pagamento"].isin(forma_sel)]
    if tipo_sel:
        df_v_todos = df_v_todos[df_v_todos["tipo_cliente"].isin(tipo_sel)]

    todos_vend = (
        df_v_todos.groupby("vendedor")
        .agg(
            total_vendido=("valor_venda", "sum"),
            comissao=("comissao", "sum"),
            num_vendas=("id", "count"),
        )
        .reset_index()
    )
    media_vendedores = todos_vend["total_vendido"].mean()

    # Top 5
    st.markdown("### Top 5 Vendedores por Faturamento")
    top5 = todos_vend.nlargest(5, "total_vendido").copy()

    fig_top5 = px.bar(
        top5, x="vendedor", y="total_vendido",
        text="total_vendido",
        title="Top 5 Vendedores",
        color="total_vendido",
        color_continuous_scale="Blues",
        labels={"vendedor": "Vendedor", "total_vendido": "Total Vendido (R$)"},
    )
    fig_top5.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
    fig_top5.update_layout(separators=SEPARATORS, yaxis_tickprefix="R$ ",
                           coloraxis_showscale=False, showlegend=False)
    st.plotly_chart(fig_top5, width="stretch")

    st.markdown("#### Tabela de Comissões (2,5%)")
    top5_fmt = top5[["vendedor", "total_vendido", "comissao", "num_vendas"]].copy()
    top5_fmt["total_vendido"] = top5_fmt["total_vendido"].apply(brl)
    top5_fmt["comissao"]      = top5_fmt["comissao"].apply(brl)
    top5_fmt["num_vendas"]    = top5_fmt["num_vendas"].apply(inteiro)
    top5_fmt.columns = ["Vendedor", "Total Vendido", "Comissão (2,5%)", "Nº de Vendas"]
    st.dataframe(top5_fmt, width="stretch", hide_index=True)

    st.divider()

    # Vendedores abaixo da média
    st.markdown("### ⚠️ Vendedores Abaixo da Média")
    st.caption(f"Média geral por vendedor: **{brl(media_vendedores)}**")

    abaixo = todos_vend[todos_vend["total_vendido"] < media_vendedores].copy()
    abaixo = abaixo.sort_values("total_vendido", ascending=True)
    abaixo["gap"]          = media_vendedores - abaixo["total_vendido"]
    abaixo["pct_da_media"] = (abaixo["total_vendido"] / media_vendedores * 100)

    fig_abaixo = px.bar(
        abaixo,
        x="total_vendido", y="vendedor",
        orientation="h",
        title=f"Vendedores Abaixo da Média — {brl(media_vendedores)}",
        color="pct_da_media",
        color_continuous_scale="RdYlGn",
        range_color=[0, 100],
        text="pct_da_media",
        labels={"vendedor": "", "total_vendido": "Total Vendido (R$)", "pct_da_media": "% da Média"},
    )
    fig_abaixo.update_traces(texttemplate="%{text:.0f}% da média", textposition="outside")
    fig_abaixo.add_vline(
        x=media_vendedores,
        line_dash="dash", line_color="red",
        annotation_text=f"Média: {brl(media_vendedores)}",
        annotation_position="top right",
    )
    fig_abaixo.update_layout(
        separators=SEPARATORS,
        xaxis_tickprefix="R$ ",
        coloraxis_showscale=False,
        height=max(450, len(abaixo) * 26),
    )
    st.plotly_chart(fig_abaixo, width="stretch")

    with st.expander(f"Ver tabela — {inteiro(len(abaixo))} vendedores abaixo da média"):
        tbl_abaixo = abaixo[["vendedor", "total_vendido", "gap", "pct_da_media", "num_vendas"]].copy()
        tbl_abaixo["total_vendido"] = tbl_abaixo["total_vendido"].apply(brl)
        tbl_abaixo["gap"]           = tbl_abaixo["gap"].apply(brl)
        tbl_abaixo["pct_da_media"]  = tbl_abaixo["pct_da_media"].apply(pct)
        tbl_abaixo["num_vendas"]    = tbl_abaixo["num_vendas"].apply(inteiro)
        tbl_abaixo.columns = ["Vendedor", "Total Vendido", "Distância da Média", "% da Média", "Nº de Vendas"]
        st.dataframe(tbl_abaixo, width="stretch", hide_index=True)

# ══════════════════════════════════════════════
# TAB 3 — Melhores Clientes
# ══════════════════════════════════════════════
with tab3:
    st.subheader("👑 Melhores Clientes por Faturamento")
    st.markdown(
        "**Pergunta do CEO:** *'Não sei quem são meus melhores clientes.'* "
        "Ranking por valor total comprado no período selecionado."
    )

    clientes = (
        df_v.groupby(["cliente", "tipo_cliente"])
        .agg(
            total_comprado=("valor_venda", "sum"),
            ticket_medio=("valor_venda", "mean"),
            num_compras=("id", "count"),
        )
        .reset_index()
        .sort_values("total_comprado", ascending=False)
    )

    top_n = st.slider("Exibir top N clientes", 5, 30, 10)
    top_cli = clientes.head(top_n).copy()

    fig_cli = px.bar(
        top_cli,
        x="total_comprado", y="cliente",
        orientation="h",
        color="tipo_cliente",
        text="total_comprado",
        title=f"Top {top_n} Clientes por Faturamento",
        labels={"total_comprado": "Total Comprado (R$)", "cliente": "", "tipo_cliente": "Tipo"},
        color_discrete_map={"Pessoa Física": "#6C63FF", "Pessoa Jurídica": "#FF6584"},
    )
    fig_cli.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
    fig_cli.update_layout(
        separators=SEPARATORS,
        xaxis_tickprefix="R$ ",
        yaxis={"categoryorder": "total ascending"},
        height=max(420, top_n * 34),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_cli, width="stretch")

    col_x, col_y = st.columns(2)
    with col_x:
        tipo_resumo = clientes.groupby("tipo_cliente")["total_comprado"].sum().reset_index()
        fig_tipo = px.pie(
            tipo_resumo,
            names="tipo_cliente", values="total_comprado",
            title="Faturamento: Pessoa Física vs Jurídica",
            hole=0.45,
            color_discrete_map={"Pessoa Física": "#6C63FF", "Pessoa Jurídica": "#FF6584"},
        )
        fig_tipo.update_layout(separators=SEPARATORS)
        st.plotly_chart(fig_tipo, width="stretch")

    with col_y:
        fig_hist = px.histogram(
            clientes, x="ticket_medio", nbins=30,
            title="Distribuição do Ticket Médio por Cliente",
            labels={"ticket_medio": "Ticket Médio (R$)", "count": "Nº de Clientes"},
            color_discrete_sequence=["#6C63FF"],
        )
        fig_hist.update_layout(separators=SEPARATORS, xaxis_tickprefix="R$ ")
        st.plotly_chart(fig_hist, width="stretch")

    with st.expander(f"Ver tabela completa (Top {top_n})"):
        tbl_cli = top_cli[["cliente", "tipo_cliente", "total_comprado", "ticket_medio", "num_compras"]].copy()
        tbl_cli["total_comprado"] = tbl_cli["total_comprado"].apply(brl)
        tbl_cli["ticket_medio"]   = tbl_cli["ticket_medio"].apply(brl)
        tbl_cli["num_compras"]    = tbl_cli["num_compras"].apply(inteiro)
        tbl_cli.columns = ["Cliente", "Tipo", "Total Comprado", "Ticket Médio", "Nº de Compras"]
        st.dataframe(tbl_cli, width="stretch", hide_index=True)

# ══════════════════════════════════════════════
# TAB 4 — Produtos
# ══════════════════════════════════════════════
with tab4:
    st.subheader("📦 Análise de Produtos por Categoria")
    st.markdown("**Pergunta:** Quais categorias têm maior margem de lucro ou volume de vendas?")

    cat_resumo = (
        df_i.groupby("categoria")
        .agg(
            volume_total=("total_venda", "sum"),
            margem_total=("margem_total", "sum"),
            qtd_itens=("quantidade", "sum"),
        )
        .reset_index()
        .sort_values("volume_total", ascending=False)
    )
    cat_resumo["margem_pct"] = (
        cat_resumo["margem_total"] / cat_resumo["volume_total"] * 100
    ).round(1).fillna(0)

    col_a, col_b = st.columns(2)
    with col_a:
        fig_vol = px.bar(
            cat_resumo, x="categoria", y="volume_total",
            text="volume_total",
            title="Volume de Vendas por Categoria (R$)",
            color="volume_total", color_continuous_scale="Greens",
            labels={"categoria": "Categoria", "volume_total": "R$ Vendido"},
        )
        fig_vol.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
        fig_vol.update_layout(separators=SEPARATORS, yaxis_tickprefix="R$ ",
                              coloraxis_showscale=False)
        st.plotly_chart(fig_vol, width="stretch")

    with col_b:
        fig_marg = px.bar(
            cat_resumo, x="categoria", y="margem_pct",
            text="margem_pct",
            title="Margem de Lucro % por Categoria",
            color="margem_pct", color_continuous_scale="Oranges",
            labels={"categoria": "Categoria", "margem_pct": "Margem (%)"},
        )
        fig_marg.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_marg.update_layout(separators=SEPARATORS, coloraxis_showscale=False)
        st.plotly_chart(fig_marg, width="stretch")

    with st.expander("Ver tabela completa por categoria"):
        tbl_cat = cat_resumo[["categoria", "volume_total", "margem_total", "margem_pct", "qtd_itens"]].copy()
        tbl_cat["volume_total"] = tbl_cat["volume_total"].apply(brl)
        tbl_cat["margem_total"] = tbl_cat["margem_total"].apply(brl)
        tbl_cat["margem_pct"]   = tbl_cat["margem_pct"].apply(pct)
        tbl_cat["qtd_itens"]    = tbl_cat["qtd_itens"].apply(inteiro)
        tbl_cat.columns = ["Categoria", "Volume Vendido", "Margem Total", "Margem (%)", "Qtd. Itens"]
        st.dataframe(tbl_cat, width="stretch", hide_index=True)

# ══════════════════════════════════════════════
# TAB 5 — Risco Financeiro (cálculo corrigido + tabela com sort numérico)
# ══════════════════════════════════════════════
with tab5:
    st.subheader("🗺️ Risco Financeiro — Inadimplência por Estado")
    st.markdown(
        "**Pergunta:** Qual é a taxa de inadimplência por Estado (UF)?\n\n"
        "**Critério:** parcela inadimplente = vencimento já passou **E** valor ainda não recebido "
        "(inclui status *ATRASADA* e *EM_ABERTO* com vencimento vencido)."
    )
    st.caption(f"📅 Data de referência: **{HOJE.strftime('%d/%m/%Y')}** — recalculada a cada abertura do painel.")
    st.info(
        f"ℹ️ Parcelas canceladas são excluídas do cálculo (não representam dívida válida). "
        f"No período selecionado: **{inteiro(df_n[df_n['cancelada']]['qtd_parcelas'].sum())}** parcelas canceladas excluídas."
    )

    # Agrupa por UF usando apenas parcelas válidas (sem CANCELADA)
    df_n_tab = df_n_valido.copy()
    inadim_grp = (
        df_n_tab.groupby(["uf", "inadimplente"])["valor_parcela"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    if True  not in inadim_grp.columns: inadim_grp[True]  = 0.0
    if False not in inadim_grp.columns: inadim_grp[False] = 0.0

    inadim_grp["total"]    = inadim_grp[True] + inadim_grp[False]
    inadim_grp["taxa_pct"] = (inadim_grp[True] / inadim_grp["total"] * 100).round(2).fillna(0)
    inadim_grp = inadim_grp.rename(columns={True: "inadimplente_val", False: "adimplente_val"})
    inadim_grp = inadim_grp[inadim_grp["uf"] != "Não Informado"].sort_values("taxa_pct", ascending=False)

    col_c, col_d = st.columns(2)

    with col_c:
        fig_uf = px.bar(
            inadim_grp.head(15),
            x="uf", y="taxa_pct",
            text="taxa_pct",
            title="Taxa de Inadimplência por UF (Top 15 — apenas ATRASADA)",
            color="taxa_pct", color_continuous_scale="Reds",
            labels={"uf": "Estado (UF)", "taxa_pct": "Taxa (%)"},
        )
        fig_uf.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_uf.update_layout(separators=SEPARATORS, coloraxis_showscale=False)
        st.plotly_chart(fig_uf, width="stretch")

    with col_d:
        fig_pizza_uf = px.pie(
            inadim_grp[inadim_grp["inadimplente_val"] > 0].head(10),
            names="uf",
            values="inadimplente_val",
            title="Distribuição do Valor Inadimplente (Top 10 UFs)",
            hole=0.45,
        )
        fig_pizza_uf.update_layout(separators=SEPARATORS)
        st.plotly_chart(fig_pizza_uf, width="stretch")

    st.markdown("#### Tabela Completa por Estado")
    tbl_uf_num = inadim_grp[["uf", "inadimplente_val", "adimplente_val", "total", "taxa_pct"]].copy()
    tbl_uf_num["inadimplente_val"] = tbl_uf_num["inadimplente_val"].apply(brl)
    tbl_uf_num["adimplente_val"]   = tbl_uf_num["adimplente_val"].apply(brl)
    tbl_uf_num["total"]            = tbl_uf_num["total"].apply(brl)
    tbl_uf_num["taxa_pct"]         = tbl_uf_num["taxa_pct"].apply(lambda x: pct(x, 2))
    tbl_uf_num.columns = ["UF", "Inadimplente", "Em Dia / A Vencer", "Total", "Taxa (%)"]
    st.dataframe(tbl_uf_num, width="stretch", hide_index=True)

# ══════════════════════════════════════════════
# TAB 6 — Formas de Pagamento
# ══════════════════════════════════════════════
with tab6:
    st.subheader("💳 Análise por Forma de Pagamento")
    st.markdown("**Pergunta:** Qual forma de pagamento gera o maior ticket médio e volume de vendas?")

    pag_resumo = (
        df_v.groupby("forma_pagamento")
        .agg(
            ticket_medio=("valor_venda", "mean"),
            total_vendido=("valor_venda", "sum"),
            num_vendas=("id", "count"),
        )
        .reset_index()
        .sort_values("ticket_medio", ascending=False)
    )

    col_e, col_f = st.columns(2)
    with col_e:
        fig_ticket = px.bar(
            pag_resumo, x="forma_pagamento", y="ticket_medio",
            text="ticket_medio",
            title="Ticket Médio por Forma de Pagamento",
            color="ticket_medio", color_continuous_scale="Teal",
            labels={"forma_pagamento": "Forma de Pagamento", "ticket_medio": "Ticket Médio (R$)"},
        )
        fig_ticket.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
        fig_ticket.update_layout(separators=SEPARATORS, yaxis_tickprefix="R$ ",
                                 coloraxis_showscale=False)
        st.plotly_chart(fig_ticket, width="stretch")

    with col_f:
        fig_vol_pag = px.pie(
            pag_resumo,
            names="forma_pagamento", values="total_vendido",
            title="Participação no Volume por Forma de Pagamento",
            hole=0.45,
        )
        fig_vol_pag.update_layout(separators=SEPARATORS)
        st.plotly_chart(fig_vol_pag, width="stretch")

    with st.expander("Ver tabela"):
        tbl_pag = pag_resumo.copy()
        tbl_pag["ticket_medio"]  = tbl_pag["ticket_medio"].apply(brl)
        tbl_pag["total_vendido"] = tbl_pag["total_vendido"].apply(brl)
        tbl_pag["num_vendas"]    = tbl_pag["num_vendas"].apply(inteiro)
        tbl_pag.columns = ["Forma de Pagamento", "Ticket Médio", "Total Vendido", "Nº de Vendas"]
        st.dataframe(tbl_pag, width="stretch", hide_index=True)

# ══════════════════════════════════════════════
# TAB 7 — IA Groq
# ══════════════════════════════════════════════
with tab7:
    st.subheader("🤖 Análise com IA — Consultor Financeiro")
    st.markdown(
        "Envia um resumo dos dados reais para a IA e recebe recomendações estratégicas "
        "para reduzir a inadimplência e melhorar o desempenho de vendas."
    )

    top_vend    = df_v.groupby("vendedor")["valor_venda"].sum().idxmax()    if len(df_v) > 0 else "N/A"
    top_cat     = df_i.groupby("categoria")["total_venda"].sum().idxmax()   if len(df_i) > 0 else "N/A"
    top_cliente = df_v.groupby("cliente")["valor_venda"].sum().idxmax()     if len(df_v) > 0 else "N/A"
    uf_top      = inadim_grp.iloc[0]["uf"]                                  if len(inadim_grp) > 0 else "N/A"
    n_abaixo    = len(abaixo)

    resumo = (
        f"Empresa: TechVendas Solutions\n"
        f"Período: {data_ini} a {data_fim}\n"
        f"- Total Vendido: {brl(total_vendido)}\n"
        f"- Ticket Médio: {brl(ticket_medio)}\n"
        f"- Clientes Únicos: {inteiro(num_clientes)}\n"
        f"- Total Inadimplente (ATRASADO): {brl(total_inadim)}\n"
        f"- Taxa de Inadimplência: {pct(taxa_inadim)}\n"
        f"- Melhor Vendedor: {top_vend}\n"
        f"- Vendedores abaixo da média: {inteiro(n_abaixo)}\n"
        f"- Categoria Campeã: {top_cat}\n"
        f"- Melhor Cliente: {top_cliente}\n"
        f"- UF com maior inadimplência: {uf_top}\n"
    )

    st.markdown("**Resumo enviado para a IA:**")
    st.info(resumo)

    if st.button("🚀 Gerar Análise com IA", type="primary"):
        try:
            groq_key = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", "")) if hasattr(st, "secrets") else os.getenv("GROQ_API_KEY", "")
            client_groq = Groq(api_key=groq_key)
            prompt = (
                "Você é um consultor financeiro sênior especializado em varejo brasileiro.\n"
                "Analise os dados abaixo e forneça:\n"
                "1. Diagnóstico da situação financeira (2-3 frases)\n"
                "2. Exatamente 3 ações práticas para reduzir a inadimplência\n"
                "3. Recomendação para melhorar a performance dos vendedores abaixo da média\n"
                "4. Uma oportunidade de crescimento com base nos dados\n\n"
                f"Dados:\n{resumo}\n\n"
                "Responda em português, de forma direta. Use tópicos numerados."
            )
            with st.spinner("Analisando dados..."):
                response = client_groq.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=1024,
                )
            st.success("Análise gerada!")
            st.markdown("### 💡 Recomendações do Consultor IA")
            st.markdown(response.choices[0].message.content)
        except Exception as e:
            st.error(f"Erro ao chamar a API Groq: {e}")

# ─────────────────────────────────────────────
# RODAPÉ
# ─────────────────────────────────────────────
st.divider()
st.caption(
    "Formação Data Analytics · Digital College · "
    "Dados: TechVendas Solutions · IA: Groq (LLaMA 4 Scout) · Felipe Rodrigues"
)
