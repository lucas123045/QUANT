"""Congelamento da regra: o que falta, a impressão digital e o registro.

Congelar é o compromisso que dá valor ao resultado: a partir da data, a regra,
os prompts, os parâmetros e o modelo não mudam, e o período de teste mede o
desempenho de algo que não foi ajustado olhando o resultado.

- `checklist()`: cada pré-requisito, com a situação e o que fazer;
- `impressao_digital()`: SHA-256 do código da regra, dos prompts, dos
  parâmetros que decidem e das fontes. Mudou qualquer um deles, muda o hash;
- `congelar()`: só pelo autor, com todos os pré-requisitos cumpridos. Grava
  congelamento.json na raiz (vai para o git) e preenche DATA_CONGELAMENTO;
- `verificar()`: confere, a cada execução, se a regra ainda é a congelada.

Uso:
    python -m src.congelamento                 # checklist e impressão digital
    python -m src.congelamento --congelar --confirmo-que-sou-o-autor
"""

import argparse
import hashlib
import inspect
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src import classify, config, extract, llm, matching, strategy

ARQUIVO = config.RAIZ_PROJETO / "congelamento.json"
FUSO = ZoneInfo(config.FUSO_REFERENCIA)
# Corte documentado pela OpenAI para o modelo do projeto (sugestão; quem registra é o autor).
CORTES_DOCUMENTADOS = {"gpt-4.1-2025-04-14": ("2024-06-01", "https://developers.openai.com/api/docs/models/gpt-4.1")}


def parametros() -> dict:
    """Tudo o que muda uma decisão ou a avaliação dela."""
    return {
        "VERSAO_REGRA": strategy.VERSAO_REGRA,
        "VERSAO_PROMPT_EXTRACAO": extract.VERSAO_PROMPT_EXTRACAO,
        "VERSAO_PROMPT_CLASSIFICACAO": classify.VERSAO_PROMPT_CLASSIFICACAO,
        "LIMIAR_PROBABILIDADE": config.LIMIAR_PROBABILIDADE,
        "MAX_POSICAO_PCT": config.MAX_POSICAO_PCT,
        "JANELA_EVENTO_RECENTE_DIAS": config.JANELA_EVENTO_RECENTE_DIAS,
        "MATERIALIDADE_MINIMA": config.MATERIALIDADE_MINIMA,
        "JANELA_REPETICAO_HORAS": config.JANELA_REPETICAO_HORAS,
        "HORA_LIMITE_EXECUCAO": list(config.HORA_LIMITE_EXECUCAO),
        "CAPITAL_INICIAL": config.CAPITAL_INICIAL,
        "CUSTOS": [config.CORRETAGEM, config.EMOLUMENTOS, config.SLIPPAGE],
        "ALFA_CRITERIO": config.ALFA_CRITERIO,
        "SEMENTE_BASELINE_2": config.SEMENTE_BASELINE_2,
        "N_SIMULACOES_BASELINE_2": config.N_SIMULACOES_BASELINE_2,
        "CARTEIRA": config.CARTEIRA,
        "BENCHMARK": config.BENCHMARK,
        "FUSO_REFERENCIA": config.FUSO_REFERENCIA,
        "PERIODOS": [config.PERIODO_TREINO, config.PERIODO_VALIDACAO, config.PERIODO_TESTE],
    }


def _texto(objeto) -> str:
    # Sem diferença de fim de linha entre Windows (CRLF) e a nuvem (LF).
    return inspect.getsource(objeto).replace("\r\n", "\n")


def impressao_digital() -> str:
    partes = {
        "regra": _texto(strategy),
        "prompt_extracao": extract.PROMPT_EXTRACAO_V2,
        "prompt_classificacao": classify.PROMPT_CLASSIFICACAO_V2,
        "casamento": [config.ALIASES, config.EXCLUSOES, config.PADROES_CONTEXTO, _texto(matching)],
        "fontes": [f["url"] for f in config.FONTES_RSS],
        "parametros": parametros(),
    }
    return hashlib.sha256(json.dumps(partes, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _modelo() -> str:
    return llm.modelo_atual().split(":", 1)[-1]


def checklist(hoje: date | None = None) -> dict:
    """Pré-requisitos do congelamento, cada um com situação e o que fazer."""
    hoje = hoje or datetime.now(FUSO).date()
    itens = []

    def item(nome, ok, detalhe, acao=None):
        itens.append({"item": nome, "ok": ok, "detalhe": detalhe, "acao": None if ok else acao})

    modelo = _modelo()
    datado = bool(re.search(r"\d{4}-\d{2}-\d{2}$", modelo))
    item("Modelo fixo, com versão datada", datado, f"modelo em uso: {modelo}",
         "Defina LLM_MODELO com a versão datada (ex.: gpt-4.1-2025-04-14), igual no .env e no GitHub.")
    corte = config.DATA_CORTE_CONHECIMENTO_MODELO
    sugestao = CORTES_DOCUMENTADOS.get(modelo)
    item("Corte de conhecimento do modelo registrado", corte is not None,
         f"registrado: {corte}" if corte else "não registrado em config.py",
         (f"Registre DATA_CORTE_CONHECIMENTO_MODELO = \"{sugestao[0]}\" em src/config.py "
          f"(documentação oficial: {sugestao[1]})." if sugestao else
          "Registre DATA_CORTE_CONHECIMENTO_MODELO em src/config.py a partir da documentação do provedor."))
    periodos = {"treino": config.PERIODO_TREINO, "validação": config.PERIODO_VALIDACAO, "teste": config.PERIODO_TESTE}
    for nome, valor in periodos.items():
        item(f"Período de {nome} aprovado", valor is not None, f"{valor[0]} a {valor[1]}" if valor else "pendente",
             f"Aprove o período de {nome} em src/config.py (formato (\"AAAA-MM-DD\", \"AAAA-MM-DD\")).")
    if corte and config.PERIODO_VALIDACAO and config.PERIODO_TESTE:
        depois = all(date.fromisoformat(p[0]) > date.fromisoformat(corte)
                     for p in (config.PERIODO_VALIDACAO, config.PERIODO_TESTE))
        item("Validação e teste começam depois do corte do modelo", depois,
             "sem risco de a IA conhecer o desfecho" if depois else "há risco de contaminação",
             "Mova o início da validação e do teste para depois do corte do modelo.")
    if config.PERIODO_TESTE:
        prospectivo = date.fromisoformat(config.PERIODO_TESTE[0]) >= hoje
        item("Teste começa no futuro (prospectivo)", prospectivo,
             f"teste começa em {config.PERIODO_TESTE[0]}",
             "O teste deve começar a partir da data do congelamento: o futuro não pode ser ajustado.")
    item("Regra com justificativa passo a passo e critérios da V3", strategy.VERSAO_REGRA == "REGRA_V3",
         f"regra vigente: {strategy.VERSAO_REGRA}")
    congelada = config.DATA_CONGELAMENTO is not None
    pendentes = [i for i in itens if not i["ok"]]
    return {"itens": itens, "pronto_para_congelar": not pendentes and not congelada,
            "congelada": congelada, "data_congelamento": config.DATA_CONGELAMENTO,
            "impressao_digital": impressao_digital(), "parametros": parametros(),
            "verificacao": verificar(),
            "comando": "python -m src.congelamento --congelar --confirmo-que-sou-o-autor"}


def verificar(arquivo: Path | None = None) -> dict:
    """A regra em uso é a congelada? (Sem congelamento, não há o que comparar.)"""
    arquivo = Path(arquivo or ARQUIVO)
    if config.DATA_CONGELAMENTO is None:
        return {"estado": "nao_congelada"}
    if not arquivo.exists():
        return {"estado": "sem_registro", "problemas": ["DATA_CONGELAMENTO preenchida, mas congelamento.json não existe"]}
    registro = json.loads(arquivo.read_text(encoding="utf-8"))
    problemas = []
    if registro.get("impressao_digital") != impressao_digital():
        problemas.append("o código da regra, um prompt, um parâmetro ou as fontes mudaram depois do congelamento")
    # O modelo só é comparado com um provedor real configurado: no modo de teste (provedor
    # falso) ou sem modelo definido, o pipeline não chama o LLM e não decide nada real.
    real = llm.provedor_atual() not in ("falso", "") and _modelo() != "nao_definido"
    if real and registro.get("modelo") != _modelo():
        problemas.append(f"o modelo em uso ({_modelo()}) não é o congelado ({registro.get('modelo')})")
    return {"estado": "integra" if not problemas else "alterada", "problemas": problemas,
            "data": registro.get("data"), "modelo": registro.get("modelo")}


def congelar(confirmado: bool, hoje: date | None = None, arquivo: Path | None = None,
             caminho_config: Path | None = None) -> dict:
    """Registra o congelamento. Só com confirmação explícita do autor e tudo cumprido."""
    hoje = hoje or datetime.now(FUSO).date()
    arquivo = Path(arquivo or ARQUIVO)
    if not confirmado:
        raise PermissionError("Congelar é decisão do autor: rode com --confirmo-que-sou-o-autor.")
    estado = checklist(hoje)
    if estado["congelada"]:
        raise RuntimeError(f"A regra já foi congelada em {config.DATA_CONGELAMENTO}.")
    pendentes = [i["item"] for i in estado["itens"] if not i["ok"]]
    if pendentes:
        raise RuntimeError("Pré-requisitos pendentes: " + "; ".join(pendentes))
    registro = {"data": hoje.isoformat(), "impressao_digital": estado["impressao_digital"], "modelo": _modelo(),
                "parametros": estado["parametros"], "registrado_em": datetime.now(FUSO).isoformat()}
    arquivo.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    caminho = Path(caminho_config or inspect.getsourcefile(config))
    texto = caminho.read_text(encoding="utf-8")
    novo, n = re.subn(r"^DATA_CONGELAMENTO = None\b", f'DATA_CONGELAMENTO = "{hoje.isoformat()}"', texto, flags=re.M)
    if n != 1:
        raise RuntimeError("Não encontrei 'DATA_CONGELAMENTO = None' em config.py para preencher.")
    caminho.write_text(novo, encoding="utf-8")
    return registro


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Congelamento da regra do QUANT.")
    parser.add_argument("--congelar", action="store_true")
    parser.add_argument("--confirmo-que-sou-o-autor", dest="confirmo", action="store_true")
    args = parser.parse_args(argv)
    llm.carregar_env()
    if args.congelar:
        registro = congelar(args.confirmo)
        print(f"Regra congelada em {registro['data']}. Impressão digital: {registro['impressao_digital']}")
        print("Faça commit de congelamento.json e src/config.py.")
        return 0
    estado = checklist()
    for i in estado["itens"]:
        print(f"[{'x' if i['ok'] else ' '}] {i['item']}: {i['detalhe']}" + (f"\n      → {i['acao']}" if i["acao"] else ""))
    print(f"\nImpressão digital da regra: {estado['impressao_digital']}")
    print("Pronto para congelar." if estado["pronto_para_congelar"] else
          ("Já congelada." if estado["congelada"] else "Ainda não está pronto para congelar."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
