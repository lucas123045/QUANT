"""Configuração central do projeto.

Parâmetros marcados como PENDENTE DE APROVAÇÃO só podem ser preenchidos pelo
autor. Parâmetros da regra (LIMIAR_PROBABILIDADE, MAX_POSICAO_PCT,
JANELA_EVENTO_RECENTE_DIAS) não mudam sem aviso prévio e ficam congelados a
partir de DATA_CONGELAMENTO.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
# Repositório no GitHub: a coleta automática na nuvem grava no ramo "dados" dele.
REPOSITORIO_GITHUB = os.environ.get("QUANT_REPOSITORIO") or "lucas123045/QUANT"
# QUANT_DATA_DIR: outra pasta de dados (na nuvem, o ramo "dados" do repositório).
DIR_DATA = Path(os.environ.get("QUANT_DATA_DIR") or RAIZ_PROJETO / "data")
DIR_ARQUIVO = DIR_DATA / "arquivo"
DIR_PRECOS = DIR_DATA / "precos"
DIR_EXECUCOES = DIR_DATA / "execucoes"
ARQUIVO_OPERACOES = DIR_DATA / "operacoes.jsonl"

# ---------------------------------------------------------------------------
# Carteira (PROVISÓRIA, escolhida em 2026-10-15; sujeita a viés de
# sobrevivência; só muda com aprovação do autor)
# ---------------------------------------------------------------------------
CARTEIRA = ["PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3"]
BENCHMARK = "^BVSP"
SUFIXO_B3 = ".SA"  # sufixo usado pelo yfinance para ações da B3

NOMES_EMPRESAS = {
    "PETR4": "Petrobras",
    "VALE3": "Vale",
    "ITUB4": "Itaú Unibanco",
    "BBDC4": "Bradesco",
    "ABEV3": "Ambev",
}

# Formas aceitas para cada empresa, comparadas sem distinção de maiúsculas e
# acentos, sempre com fronteira de palavra. O próprio ticker é aceito
# automaticamente (com sufixo opcional "F" do mercado fracionário).
# "Vale" sozinho NÃO está aqui de propósito: é palavra comum ("vale a pena").
ALIASES = {
    "PETR4": ["Petrobras", "Petróleo Brasileiro", "PETR3"],
    "VALE3": ["Vale S.A.", "Vale SA", "Vale do Rio Doce", "mineradora Vale"],
    "ITUB4": ["Itaú Unibanco", "Itaú", "Banco Itaú", "ITUB3"],
    "BBDC4": ["Bradesco", "Banco Bradesco", "BBDC3"],
    "ABEV3": ["Ambev"],
}

# Expressões removidas do texto antes do casamento (sem distinção de caixa e
# acentos). Casas de análise ligadas aos bancos aparecem como FONTE de opinião
# sobre outras empresas ("segundo o Itaú BBA, ...") e não como notícia do banco.
EXCLUSOES = {
    "ITUB4": ["Itaú BBA"],
    "BBDC4": ["Bradesco BBI"],
}

# Padrões de contexto (expressões regulares sensíveis a maiúsculas, aplicadas
# ao texto original). Aceitam "Vale" com V maiúsculo apenas quando precedido
# de artigo/preposição ("a Vale", "da Vale", "pela Vale"...), e nunca quando
# seguido de "do"/"dos" (ex.: "Vale do Silício"), exceto "Vale do Rio Doce",
# que já é alias.
PADROES_CONTEXTO = {
    "VALE3": [
        r"\b(?:[AaÀà]|[Dd]a|[Nn]a|[Pp]ela|[Cc]om a|[Pp]ara a)\s+Vale\b(?!\s+d[oa]s?\b)",
    ],
}

# ---------------------------------------------------------------------------
# Regra de decisão (congelada na DATA_CONGELAMENTO; não alterar sem aviso)
# ---------------------------------------------------------------------------
LIMIAR_PROBABILIDADE = 0.7          # compra/venda exigem probabilidade ESTRITAMENTE acima
MAX_POSICAO_PCT = 0.20              # fração máxima do patrimônio por ação
CAPITAL_INICIAL = 100_000.0
JANELA_EVENTO_RECENTE_DIAS = 5      # dias corridos para "evento oposto recente"

# ---------------------------------------------------------------------------
# Custos: zerados por padrão. Frações do valor negociado (0.001 = 0,1%).
# Não preencher sem fonte verificada.
# ---------------------------------------------------------------------------
CORRETAGEM = 0.0
EMOLUMENTOS = 0.0
SLIPPAGE = 0.0

# ---------------------------------------------------------------------------
# Períodos: PENDENTE DE APROVAÇÃO. Formato quando aprovado: ("AAAA-MM-DD", "AAAA-MM-DD").
# ---------------------------------------------------------------------------
PERIODO_TREINO = None       # PENDENTE DE APROVAÇÃO
PERIODO_VALIDACAO = None    # PENDENTE DE APROVAÇÃO
PERIODO_TESTE = None        # PENDENTE DE APROVAÇÃO (precisa de data final fixa)
DATA_CONGELAMENTO = None    # PENDENTE: preenchida só pelo autor ao congelar a regra

# ---------------------------------------------------------------------------
# Critério de decisão (congela junto com a regra)
# ---------------------------------------------------------------------------
# Nível de significância dos testes t unilaterais do critério (seção 3 do README).
ALFA_CRITERIO = 0.05

# ---------------------------------------------------------------------------
# Contaminação por conhecimento do LLM
# ---------------------------------------------------------------------------
# Data de corte de conhecimento do modelo usado na extração ("AAAA-MM-DD"),
# tirada da documentação oficial do provedor. PENDENTE: preencher ao escolher
# o modelo. Períodos que começam antes dela podem ter look-ahead via modelo.
DATA_CORTE_CONHECIMENTO_MODELO = None

# ---------------------------------------------------------------------------
# Corte temporal
# ---------------------------------------------------------------------------
FUSO_REFERENCIA = "America/Sao_Paulo"
# Evento publicado em qualquer horário do dia D (fuso de referência) é
# executado no fechamento do primeiro pregão ESTRITAMENTE posterior a D.
# Assim, publicação após o fechamento entra no pregão seguinte, e publicação
# durante o pregão também, o que evita usar informação intradiária que o
# backtest com preços de fechamento não consegue datar com segurança.

# ---------------------------------------------------------------------------
# Baseline 2 (sorteio)
# ---------------------------------------------------------------------------
SEMENTE_BASELINE_2 = 20261015
N_SIMULACOES_BASELINE_2 = 1000

# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------
# "nome" é o portal (contagens e alertas são por portal); "feed" diz qual feed.
# Os feeds gerais trazem sobretudo política e mundo: em 20/10/2026, só 5 de 96
# notícias citavam a carteira. Os feeds por empresa (tag) dos mesmos portais
# trazem 90% a 100% de notícias da empresa e cobrem cerca de uma semana.
# A Ambev não tem feed próprio no InfoMoney (404); o feed geral cobre.
FONTES_RSS = [
    {"nome": "InfoMoney", "feed": "geral", "url": "https://www.infomoney.com.br/feed/"},
    {"nome": "Money Times", "feed": "geral", "url": "https://www.moneytimes.com.br/feed/"},
    {"nome": "InfoMoney", "feed": "PETR4", "url": "https://www.infomoney.com.br/tudo-sobre/petrobras/feed/"},
    {"nome": "InfoMoney", "feed": "VALE3", "url": "https://www.infomoney.com.br/tudo-sobre/vale/feed/"},
    {"nome": "InfoMoney", "feed": "ITUB4", "url": "https://www.infomoney.com.br/tudo-sobre/itau-unibanco/feed/"},
    {"nome": "InfoMoney", "feed": "BBDC4", "url": "https://www.infomoney.com.br/tudo-sobre/bradesco/feed/"},
    {"nome": "Money Times", "feed": "PETR4", "url": "https://www.moneytimes.com.br/tag/petrobras/feed/"},
    {"nome": "Money Times", "feed": "VALE3", "url": "https://www.moneytimes.com.br/tag/vale/feed/"},
    {"nome": "Money Times", "feed": "ITUB4", "url": "https://www.moneytimes.com.br/tag/itau/feed/"},
    {"nome": "Money Times", "feed": "BBDC4", "url": "https://www.moneytimes.com.br/tag/bradesco/feed/"},
    {"nome": "Money Times", "feed": "ABEV3", "url": "https://www.moneytimes.com.br/tag/ambev/feed/"},
]
JANELA_COLETA_HORAS = 24

# ---------------------------------------------------------------------------
# Classificação e LLM
# ---------------------------------------------------------------------------
USAR_JEV = False  # Jev é opcional; acesso à API ainda não confirmado

# ===========================================================================
# CAMADA PRÁTICA (fora da pesquisa)
# ===========================================================================
# Como um investidor de verdade operaria as MESMAS decisões da regra: com custos
# da B3, imposto de renda, tamanho de posição pelo risco, limite por setor, saída
# por prazo e por perda, e o caixa rendendo CDI. É outra carteira, mostrada ao
# lado da carteira da pesquisa (src/pratica.py). Nada aqui altera a regra
# congelada acima nem o critério de decisão do trabalho.
VERSAO_PRATICA = "PRATICA_V1"

# Custos por lado (compra e venda), frações do valor negociado.
# B3, "Tarifas de ações e fundos de investimento - à vista", consultada em
# 21/10/2026: negociação 0,005% (0,007% nos leilões de abertura e fechamento),
# CCP 0,0224% e TTA 0,0026%, para ADTV mensal de até R$ 3 milhões. O QUANT
# executa no fechamento, ou seja, no leilão de fechamento: 0,007 + 0,0224 + 0,0026.
PRATICA_EMOLUMENTOS = 0.00032
# Corretagem: zero nas principais corretoras para ações (ajuste se a sua cobra).
PRATICA_CORRETAGEM = 0.0
# Sem spread: o leilão de fechamento tem preço único. Uma ordem de ~R$ 20 mil é
# irrelevante perto do volume diário destas ações (bilhões de reais).
PRATICA_SLIPPAGE = 0.0

# Imposto de renda em operações comuns (swing trade) com ações. Lei 11.033/2004
# e IN RFB 1.585/2015; a MP 1.303/2025, que mudaria isso, caducou em 08/10/2025.
# - 15% sobre o lucro líquido do mês;
# - isento no mês em que o TOTAL VENDIDO em ações não passa de R$ 20 mil;
# - prejuízo fica acumulado e abate lucro tributável dos meses seguintes
#   (interpretação usada pela calculadora ReVar da Receita/B3; confirme com um
#   contador se for declarar). O IR retido de 0,005% ("dedo-duro") é só
#   antecipação e não muda o resultado.
PRATICA_IR_ALIQUOTA = 0.15
PRATICA_IR_ISENCAO_VENDAS_MES = 20_000.0

# Tamanho da posição pelo risco: a regra manda até 20% (MAX_POSICAO_PCT); a
# prática dá 20% a uma ação que oscila como a referência e menos às mais
# voláteis, para cada posição pesar o mesmo risco na carteira:
#   peso = min(MAX_POSICAO_PCT, MAX_POSICAO_PCT * referência / volatilidade da ação)
# Referência: 25% ao ano, perto da volatilidade histórica do Ibovespa.
PRATICA_VOL_REFERENCIA_ANUAL = 0.25
PRATICA_JANELA_VOL_PREGOES = 60      # ~3 meses de pregões para estimar a volatilidade

# Limite por setor (classificação setorial da B3). Itaú e Bradesco andam muito
# juntos: duas posições cheias em bancos seriam quase a mesma aposta duas vezes.
SETORES = {"PETR4": "Petróleo e gás", "VALE3": "Mineração", "ITUB4": "Bancos",
           "BBDC4": "Bancos", "ABEV3": "Bebidas"}
PRATICA_LIMITE_SETOR = 0.30

# Saídas (a regra só vende com notícia negativa, o que na prática segura a
# posição para sempre):
# - por prazo: o efeito de uma notícia, quando existe, costuma se esgotar em
#   dias ou semanas; 20 pregões (~1 mês) é o horizonte mais longo do estudo de
#   evento. A rever quando o estudo de evento tiver amostra.
# - por perda: sai se a perda passar de 2 desvios-padrão do retorno esperado em
#   20 pregões (vol diária x raiz de 20), medido na compra. Corta só perdas fora
#   do comum, não o ruído do dia a dia. Checado no fechamento.
PRATICA_PRAZO_MAXIMO_PREGOES = 20
PRATICA_STOP_DESVIOS = 2.0

# Reação do mercado como confirmação da surpresa: retorno da ação menos o do
# Ibovespa, do fechamento antes da notícia ao fechamento anterior à execução,
# medido em desvios-padrão desse excesso nos 60 pregões anteriores.
# |z| > 2: reação fora do comum (~5% de chance por acaso, o corte usual em
# estudo de evento). Notícia positiva com reação forte CONTRA (z < -2): o
# mercado leu como surpresa ruim, a prática não compra (e o espelho na venda).
# Reação forte A FAVOR não bloqueia: movimentos causados por notícia tendem a
# continuar (Chan, 2003, J. Financial Economics); o estudo de evento mede isso.
PRATICA_Z_REACAO = 2.0

# ---------------------------------------------------------------------------
# Fatos relevantes da CVM (dados abertos, src/cvm.py)
# ---------------------------------------------------------------------------
# Documentos entregues à CVM (IPE), filtrados por CNPJ e categoria "Fato
# Relevante". A data de entrega vem sem hora e o arquivo é atualizado com alguns
# dias de atraso: serve como fonte primária e confirmação, não como furo.
URL_CVM_IPE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"
CNPJ_CARTEIRA = {
    "33.000.167/0001-01": "PETR4",  # Petróleo Brasileiro S.A. - Petrobras
    "33.592.510/0001-54": "VALE3",  # Vale S.A.
    "60.872.504/0001-23": "ITUB4",  # Itaú Unibanco Holding S.A.
    "60.746.948/0001-12": "BBDC4",  # Banco Bradesco S.A.
    "07.526.557/0001-00": "ABEV3",  # Ambev S.A.
}
JANELA_CVM_DIAS = 10    # dias de entrega a revisar a cada coleta (o arquivo atrasa)

# ---------------------------------------------------------------------------
# Contexto de mercado (src/mercado.py): só para leitura, não entra na regra
# ---------------------------------------------------------------------------
# ADRs negociados em Nova York (PETR4 é preferencial: PBR-A; PBR é a ordinária).
ADRS = {"PETR4": "PBR-A", "VALE3": "VALE", "ITUB4": "ITUB", "BBDC4": "BBD", "ABEV3": "ABEV"}
# Séries do SGS (Banco Central): meta Selic, IPCA acumulado em 12 meses, dólar PTAX venda.
SERIES_BCB = {"selic": 432, "ipca_12m": 13522, "dolar_ptax": 1}
# Commodities que mais pesam em PETR4 e VALE3 (yfinance): Brent e minério de ferro 62% (SGX).
COMMODITIES = {"brent": "BZ=F", "minerio": "TIO=F"}
# Reuniões do Copom em 2026 (calendário publicado pelo Banco Central em junho de
# 2025). A decisão sai no fim do segundo dia, por volta das 18h30.
COPOM_2026 = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
              "2026-08-05", "2026-09-16", "2026-11-04", "2026-12-09"]
