"""Configuração central do projeto.

Parâmetros marcados como PENDENTE DE APROVAÇÃO só podem ser preenchidos pelo
autor. Parâmetros da regra (LIMIAR_PROBABILIDADE, MAX_POSICAO_PCT,
JANELA_EVENTO_RECENTE_DIAS) não mudam sem aviso prévio e ficam congelados a
partir de DATA_CONGELAMENTO.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
DIR_DATA = RAIZ_PROJETO / "data"
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
FONTES_RSS = [
    {"nome": "InfoMoney", "url": "https://www.infomoney.com.br/feed/"},
    {"nome": "Money Times", "url": "https://www.moneytimes.com.br/feed/"},
]
JANELA_COLETA_HORAS = 24

# ---------------------------------------------------------------------------
# Classificação e LLM
# ---------------------------------------------------------------------------
USAR_JEV = False  # Jev é opcional; acesso à API ainda não confirmado
