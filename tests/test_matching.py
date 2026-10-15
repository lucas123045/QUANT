import pytest

from src.matching import identificar_tickers, menciona, normalizar


def test_normalizar_remove_acento_maiuscula_e_espacos():
    assert normalizar("  Itaú   UNIBANCO\n") == "itau unibanco"


# --- "vale" palavra comum nunca é VALE3 -------------------------------------

@pytest.mark.parametrize("frase", [
    "vale a pena investir em renda fixa",
    "Vale a pena investir agora?",
    "O cupom vale até sexta-feira",
    "Isso vale para todos os bancos",
    "o valor da ação caiu",
    "Startups do Vale do Silício captam recursos",
    "vale-refeição sobe 10%",
])
def test_vale_palavra_comum_nao_casa(frase):
    assert not menciona(frase, "VALE3")


@pytest.mark.parametrize("frase", [
    "a Vale divulgou resultado do trimestre",
    "Lucro da Vale supera estimativas",
    "Vale S.A. aprova recompra",
    "Ações da mineradora Vale disparam",
    "Companhia Vale do Rio Doce foi privatizada em 1997",
    "VALE3 fecha em alta",
])
def test_vale_empresa_casa(frase):
    assert menciona(frase, "VALE3")


def test_vale_no_inicio_de_manchete_sem_contexto_e_ambiguo_e_nao_casa():
    # Caso ambíguo: "Vale" no início da frase pode ser empresa ou verbo.
    # A regra conservadora não aceita sem contexto.
    assert not menciona("Vale anuncia dividendos", "VALE3")
    assert menciona("Vale (VALE3) anuncia dividendos", "VALE3")


# --- tickers com fronteira de palavra ---------------------------------------

@pytest.mark.parametrize("frase,ticker", [
    ("PETR4 sobe 3% no pregão", "PETR4"),
    ("petr4 sobe", "PETR4"),
    ("Compra de PETR4F no fracionário", "PETR4"),
    ("(ITUB4) avança", "ITUB4"),
    ("ABEV3, BBDC4 e ITUB4 lideram", "BBDC4"),
])
def test_ticker_com_fronteira_casa(frase, ticker):
    assert menciona(frase, ticker)


@pytest.mark.parametrize("frase,ticker", [
    ("código XPETR4 inválido", "PETR4"),
    ("PETR45 não é ticker", "PETR4"),
    ("ITUB40 não existe", "ITUB4"),
    ("token ABEV3X", "ABEV3"),
    ("arquivo_BBDC4", "BBDC4"),
])
def test_ticker_dentro_de_outra_palavra_nao_casa(frase, ticker):
    assert not menciona(frase, ticker)


# --- nomes e aliases ---------------------------------------------------------

@pytest.mark.parametrize("frase,ticker", [
    ("Petrobras amplia produção no pré-sal", "PETR4"),
    ("PETROBRAS anuncia dividendos", "PETR4"),
    ("Petróleo Brasileiro S.A. divulga fato relevante", "PETR4"),
    ("Itaú Unibanco reporta lucro", "ITUB4"),
    ("Itau eleva projeção", "ITUB4"),
    ("Bradesco corta custos", "BBDC4"),
    ("Ambev lança cerveja", "ABEV3"),
])
def test_nome_e_alias_casam(frase, ticker):
    assert menciona(frase, ticker)


@pytest.mark.parametrize("frase,ticker", [
    ("Itaúsa recebe proventos", "ITUB4"),        # holding diferente
    ("Bradespar vende participação", "BBDC4"),   # empresa diferente
    ("Petrobrasileira fictícia", "PETR4"),
    ("ambevzinha", "ABEV3"),
])
def test_nome_como_parte_de_outra_palavra_nao_casa(frase, ticker):
    assert not menciona(frase, ticker)


def test_identificar_tickers_varias_empresas():
    texto = "Petrobras e a Vale puxam o Ibovespa; Bradesco recua."
    assert identificar_tickers(texto) == ["PETR4", "VALE3", "BBDC4"]


def test_identificar_tickers_texto_vazio():
    assert identificar_tickers("") == []
    assert identificar_tickers("vale a pena esperar o Copom") == []


# --- casas de análise como fonte de opinião ----------------------------------

@pytest.mark.parametrize("frase,ticker", [
    ("Ação da TIM está barata, diz o Itaú BBA", "ITUB4"),
    ("Analistas do Bradesco BBI recomendam Azzas", "BBDC4"),
    ("itau bba eleva preço-alvo da Magalu", "ITUB4"),
])
def test_casa_de_analise_nao_conta_como_mencao(frase, ticker):
    assert not menciona(frase, ticker)


def test_banco_citado_tambem_fora_da_casa_de_analise_casa():
    assert menciona("Itaú BBA vê alta; o Itaú Unibanco reporta lucro", "ITUB4")
