"""
database.py — Etapa A: Extração e Conexão (SQL & Banco de Dados)
Responsável por conectar ao banco PostgreSQL e executar todas as queries.
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def _secret(key: str, default: str = "") -> str:
    """Lê credencial do Streamlit Cloud (st.secrets) ou do .env local."""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)

def get_engine():
    host     = _secret("DB_HOST",     "postgresql-datadt.alwaysdata.net")
    dbname   = _secret("DB_NAME",     "datadt_digital_corporativo")
    user     = _secret("DB_USER",     "datadt_data_analytics")
    password = _secret("DB_PASSWORD", "DataAnalytics$100")
    url = f"postgresql+psycopg2://{user}:{password}@{host}/{dbname}"
    return create_engine(url)


# ─────────────────────────────────────────────
# QUERY 1 — Vendas completas com vendedor, cliente e UF
# JOIN: vendas.nota_fiscal + geral.pessoa_fisica/juridica + geral.endereco + geral.estado
# ─────────────────────────────────────────────
def carregar_vendas() -> pd.DataFrame:
    """
    Retorna DataFrame com todas as notas fiscais, incluindo:
    nome do vendedor, nome do cliente, tipo de pessoa,
    estado (UF) do cliente e forma de pagamento.
    """
    query = """
    WITH pessoa_estado AS (
        -- Garante apenas 1 UF por pessoa (evita duplicatas de endereço)
        SELECT DISTINCT ON (end_cli.id_pessoa)
            end_cli.id_pessoa,
            est.sigla AS uf
        FROM geral.endereco end_cli
        LEFT JOIN geral.bairro    b   ON end_cli.id_bairro = b.id
        LEFT JOIN geral.cidade    cid ON b.id_cidade       = cid.id
        LEFT JOIN geral.estado    est ON cid.id_estado     = est.id
        ORDER BY end_cli.id_pessoa, end_cli.id
    )
    SELECT
        nf.id,
        nf.numero_nf,
        nf.data_venda,
        nf.valor,
        -- Vendedor pode ser PF ou PJ
        COALESCE(pf_vend.nome, pj_vend.razao_social)           AS vendedor,
        -- Cliente pode ser PF ou PJ
        COALESCE(pf_cli.nome,  pj_cli.razao_social)            AS cliente,
        CASE
            WHEN pf_cli.id IS NOT NULL THEN 'Pessoa Física'
            ELSE 'Pessoa Jurídica'
        END                                                     AS tipo_cliente,
        pe.uf,
        fp.descricao                                            AS forma_pagamento
    FROM vendas.nota_fiscal nf
    LEFT JOIN geral.pessoa_fisica   pf_vend ON nf.id_vendedor  = pf_vend.id
    LEFT JOIN geral.pessoa_juridica pj_vend ON nf.id_vendedor  = pj_vend.id
    LEFT JOIN geral.pessoa_fisica   pf_cli  ON nf.id_cliente   = pf_cli.id
    LEFT JOIN geral.pessoa_juridica pj_cli  ON nf.id_cliente   = pj_cli.id
    LEFT JOIN pessoa_estado         pe      ON nf.id_cliente   = pe.id_pessoa
    LEFT JOIN vendas.forma_pagamento fp     ON nf.id_forma_pagto = fp.id
    ORDER BY nf.data_venda
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df


# ─────────────────────────────────────────────
# QUERY 2 — Itens de venda com categoria e margem de lucro
# JOIN: vendas.item_nota_fiscal + vendas.produto + vendas.categoria + vendas.nota_fiscal
# ─────────────────────────────────────────────
def carregar_itens() -> pd.DataFrame:
    """
    Retorna DataFrame com os itens de cada venda, incluindo:
    produto, categoria, quantidade, preço de venda, custo e margem calculada.
    """
    query = """
    SELECT
        inf.id_nota_fiscal,
        nf.data_venda,
        p.nome                                      AS produto,
        cat.descricao                               AS categoria,
        inf.quantidade,
        inf.valor_unitario                          AS preco_venda,
        p.valor_custo                               AS custo,
        inf.valor_venda_real                        AS total_venda,
        (inf.valor_unitario - p.valor_custo)        AS margem_unitaria,
        (inf.valor_unitario - p.valor_custo)
            * inf.quantidade                        AS margem_total
    FROM vendas.item_nota_fiscal inf
    JOIN vendas.produto          p   ON inf.id_produto      = p.id
    JOIN vendas.categoria        cat ON p.id_categoria      = cat.id
    JOIN vendas.nota_fiscal      nf  ON inf.id_nota_fiscal  = nf.id
    ORDER BY nf.data_venda
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df


# ─────────────────────────────────────────────
# QUERY 3 — Inadimplência por cliente e estado
# Substituímos a view por joins diretos para obter o campo vencimento,
# que é essencial para classificar inadimplência pela data de hoje.
# Lógica:
#   - LIQUIDADA                          → pago
#   - EM_ABERTO + vencimento >= hoje     → dentro do prazo
#   - EM_ABERTO + vencimento <  hoje     → inadimplente (sistema não atualizou)
#   - ATRASADA                           → inadimplente
# ─────────────────────────────────────────────
def carregar_inadimplencia() -> pd.DataFrame:
    """
    Retorna DataFrame com todas as parcelas, incluindo data de vencimento,
    para permitir cálculo dinâmico de inadimplência baseado na data atual.
    """
    query = """
    WITH pessoa_estado AS (
        SELECT DISTINCT ON (end_cli.id_pessoa)
            end_cli.id_pessoa,
            est.sigla AS uf
        FROM geral.endereco end_cli
        LEFT JOIN geral.bairro    b   ON end_cli.id_bairro = b.id
        LEFT JOIN geral.cidade    cid ON b.id_cidade       = cid.id
        LEFT JOIN geral.estado    est ON cid.id_estado     = est.id
        ORDER BY end_cli.id_pessoa, end_cli.id
    )
    SELECT
        nf.numero_nf,
        nf.data_venda,
        nf.valor                                                    AS valor_venda,
        COALESCE(pf.nome, pj.razao_social)                          AS cliente,
        CASE WHEN pf.id IS NOT NULL THEN 'Pessoa Física'
             ELSE 'Pessoa Jurídica' END                             AS tipo_pessoa,
        parc.valor                                                  AS valor_parcela,
        fp.descricao                                                AS forma_pagamento,
        parc.numero                                                 AS numero_parcela,
        st.descricao                                                AS situacao,
        cr.vencimento,
        pe.uf
    FROM vendas.nota_fiscal       nf
    JOIN vendas.parcela           parc ON parc.id_nota_fiscal = nf.id
    JOIN financeiro.conta_receber cr   ON cr.id_parcela       = parc.id
    JOIN financeiro.situacao_titulo st ON cr.id_situacao      = st.id
    LEFT JOIN vendas.forma_pagamento fp ON nf.id_forma_pagto  = fp.id
    LEFT JOIN geral.pessoa_fisica   pf ON nf.id_cliente       = pf.id
    LEFT JOIN geral.pessoa_juridica pj ON nf.id_cliente       = pj.id
    LEFT JOIN pessoa_estado         pe ON nf.id_cliente       = pe.id_pessoa
    ORDER BY nf.data_venda
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    return df
