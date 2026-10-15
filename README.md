# QUANT

Trabalho acadêmico. Sistema que lê notícias e fatos relevantes sobre uma carteira fixa de ações da B3, usa um LLM generativo para extrair eventos estruturados, aplica uma regra de decisão determinística e testável, e compara o resultado com o Ibovespa (comprar e segurar).

## 1. Objetivo e hipótese

**Objetivo:** verificar se eventos extraídos automaticamente de textos (notícias e fatos relevantes) por um LLM generativo produzem um sinal de negociação que supera alternativas simples.

**Hipótese central:** notícias e anúncios contêm informação ainda não precificada pelo mercado, e um extrator automático consegue capturá-la com antecedência útil.

**Papel da IA generativa:** é indispensável ao sistema, não decorativa. Sem o LLM não existem eventos estruturados (tipo de evento, impacto declarado, confirmação, trecho de origem) a partir do texto livre, e portanto não existe entrada para a regra de decisão. O LLM tem dois papéis, e só esses dois:

- **extrair** eventos estruturados do texto (`src/extract.py`);
- **explicar** em linguagem natural decisões já tomadas (`src/explain.py`).

O LLM **nunca** decide compra ou venda. A decisão vem exclusivamente de `src/strategy.py`, que é determinística e coberta por testes.

## 2. Hipótese por fonte

As duas fontes são testadas separadamente, cada uma com sua hipótese:

| Fonte | Hipótese |
|---|---|
| **Fatos relevantes (CVM)** | O preço da ação reage de forma previsível ao anúncio oficial da companhia nos pregões seguintes à divulgação. |
| **Notícias de portal** | O preço da ação reage de forma previsível à cobertura jornalística sobre a empresa, classificada pelo extrator. |

Uma regra calibrada em uma fonte **não é automaticamente válida** na outra. Nenhum teste mistura as duas fontes sem registrar a origem de cada evento (campo de tipo de fonte: `fato_relevante` ou `noticia`).

## 3. Critério de decisão

A estratégia só é considerada **útil** se, no período de teste, cumprir as três condições abaixo:

1. superar o baseline "comprar qualquer notícia positiva";
2. superar o Ibovespa (comprar e segurar);
3. ter as duas diferenças, já descontados os custos, maiores que o erro padrão da média do retorno por operação.

Se não superar, o trabalho conclui que **o sinal não foi demonstrado**. Esse é um resultado válido e será reportado como tal.

> Os custos são os configurados em `src/config.py`. Hoje estão zerados (ver seção 8), então o resultado "líquido" é igual ao bruto até que valores de custo sejam aprovados.

## 4. Métricas

- **Primária:** retorno acumulado líquido da estratégia contra o Ibovespa no período de teste.
- **Secundárias:** volatilidade e drawdown máximo.
- **Apoio ao critério:** erro padrão da média do retorno por operação (desvio-padrão ÷ √número de operações).

## 5. Data de congelamento da regra

Antes de olhar qualquer resultado do período de teste, a regra é congelada. A partir daí, os itens abaixo não podem mudar:

- `LIMIAR_PROBABILIDADE` (hoje 0,7)
- `MAX_POSICAO_PCT` (hoje 0,20)
- `JANELA_EVENTO_RECENTE_DIAS` (hoje 5), usado pela lógica de `decidir`
- lógica da função `decidir` (`src/strategy.py`, `REGRA_V1`)
- prompt de extração (`PROMPT_EXTRACAO_V1`, `src/extract.py`)
- prompt de classificação (`PROMPT_CLASSIFICACAO_V1`, `src/classify.py`)
- versão do modelo de LLM usado (`LLM_PROVEDOR` e `LLM_MODELO`)
- carteira, aliases e exclusões do casamento de tickers (`src/config.py`)
- semente do baseline 2 (`SEMENTE_BASELINE_2 = 20261015`)

O código impede rodar o período de teste enquanto `DATA_CONGELAMENTO` for `None`: `periodo_do_config("teste")` levanta `CongelamentoPendente`.

| Campo | Valor |
|---|---|
| Data de congelamento | _PENDENTE_ |
| Hash do commit | _PENDENTE_ |
| Aprovação | _PENDENTE_ |

Esses campos são preenchidos apenas pelo autor.

## 6. Posição sobre o Jev

- O Jev é um **classificador opcional** (sentimento e probabilidade), acessado apenas pela interface de `src/classify.py`.
- O **LLM generativo é o plano B** e é um caminho normal de execução, não uma exceção. Nenhuma funcionalidade depende do Jev.
- O Jev nunca é camada de decisão.
- Enquanto não houver especificação da API no repositório, o adaptador do Jev fica como `NotImplementedError`.
- **Pendência:** confirmar o acesso à API do Jev. Se não houver acesso até _[data a definir]_, o projeto segue apenas com o LLM.

## 7. Fuso e corte temporal

- **Fuso de referência:** `America/Sao_Paulo`.
- **Regra:** uma notícia ou um fato relevante publicado **após o fechamento do pregão da B3** entra no **pregão do dia seguinte**.
- **Regra de implementação:** um evento publicado em qualquer horário do dia D, no fuso de referência, é executado no **fechamento do primeiro pregão estritamente posterior a D**. Isso cumpre a regra acima e também trata da mesma forma os eventos publicados **durante** o pregão. Como o backtest usa apenas preços de fechamento, executar no fechamento do próprio dia D poderia usar um preço que já refletia a notícia (olhar o futuro).
- Com essa regra, o horário exato de fechamento da B3, que muda ao longo do ano, não afeta a execução.
- Fins de semana e feriados: o calendário de pregões é o do Ibovespa (`^BVSP`) no yfinance, então o evento vai para o próximo dia com negociação.

## 8. Escopo e limitações

- **Não é tempo real:** é um pipeline diário, em lote. _Pendente de confirmação com o professor._
- **Custos zerados:** corretagem, emolumentos e slippage estão em zero por padrão, como parâmetros explícitos em `src/config.py`. Nenhum valor foi inventado.
- **Impostos não modelados:** não há alíquotas no modelo sem verificação com um contador.
- **Viés de sobrevivência:** a carteira foi escolhida hoje, com conhecimento de quais empresas continuam grandes e listadas. Isso tende a favorecer os resultados históricos.
- **Poder estatístico baixo:** com poucas operações, o erro padrão é grande e diferenças pequenas não são distinguíveis de ruído.
- **Simplificações do backtest:**
  - ações fracionárias são permitidas;
  - não há venda a descoberto (VENDA só zera uma posição existente);
  - os preços são fechamentos ajustados por proventos (yfinance, `auto_adjust=True`);
  - posições abertas no fim do período são liquidadas teoricamente no último fechamento;
  - o erro padrão é calculado por operação, enquanto as diferenças do critério são de retorno acumulado. É uma comparação conservadora e simples, adotada como foi especificada.
- **Arquivo de notícias:** só existe a partir da data de início da coleta. Os feeds RSS trazem apenas itens recentes, então não há histórico retroativo de notícias de portal.

### Carteira provisória

| Ticker | Empresa |
|---|---|
| PETR4 | Petrobras |
| VALE3 | Vale |
| ITUB4 | Itaú Unibanco |
| BBDC4 | Bradesco |
| ABEV3 | Ambev |

A carteira é **provisória** e foi **escolhida hoje** (2026-10-15), portanto está sujeita a viés de sobrevivência. Ela só pode ser alterada com aprovação do autor.

## 9. Períodos

| Período | Início | Fim | Status |
|---|---|---|---|
| Treino | — | — | PENDENTE DE APROVAÇÃO |
| Validação | — | — | PENDENTE DE APROVAÇÃO |
| Teste | — | — | PENDENTE DE APROVAÇÃO |

Em `src/config.py`, os períodos ficam como `None` até a aprovação. Nenhum backtest roda com período `None`.

## 10. Pendências

- [ ] Arquivar notícias e fatos relevantes com timestamp e fonte (**prioridade 1**).
  - **Notícias de portal:** a ferramenta está pronta (`python -m src.archive --coletar`) e a primeira coleta real foi feita em 2026-10-15, com 20 itens. Falta agendar a execução diária; o agendamento só será configurado depois da aprovação. Início oficial do arquivamento: _[data a definir]_.
  - **Fatos relevantes:** bloqueados até a verificação da CVM (item abaixo).
- [ ] Verificar se a CVM tem histórico utilizável de fatos relevantes para as 5 ações, com data de entrega confiável. O adaptador `coletar_fatos_relevantes` fica como `NotImplementedError` até lá.
- [ ] Aprovar datas de treino, validação e teste
- [ ] Definir a data de congelamento da regra
- [ ] Confirmar acesso à API do Jev. Enquanto isso, o LLM é o classificador e `USAR_JEV = False`.
- [ ] Definir o provedor e o modelo do LLM, e registrar o provedor em `src/llm.py`. Sem isso, o pipeline real arquiva as notícias, mas não extrai eventos.
- [ ] Confirmar "tempo real" com o professor
- [ ] Confirmar a carteira
- [ ] Verificar aspectos tributários com contador (não modelar alíquotas sem verificação)

## 11. Arquitetura

```
coletar (news.py) → arquivar (archive.py) → extrair + validar trecho (extract.py, LLM)
  → classificar (classify.py: Jev opcional | LLM) → decidir (strategy.py, determinístico)
  → explicar (explain.py, LLM) → registrar (auditoria.py → data/operacoes.jsonl) → relatório
```

| Módulo | Papel |
|---|---|
| `src/config.py` | Carteira, parâmetros da regra, custos, períodos, fontes |
| `src/matching.py` | Decide se um texto menciona uma empresa da carteira. Usa o ticker com fronteira de palavra, o nome e os aliases; "vale" isolado nunca casa; casas de análise como "Itaú BBA" são excluídas |
| `src/news.py` | Coleta RSS (InfoMoney e Money Times) das últimas 24 h, tolerando falhas por fonte. A CVM está bloqueada |
| `src/archive.py` | Arquivo append-only em `data/arquivo/AAAA-MM-DD.jsonl` (data da coleta), com deduplicação por URL |
| `src/llm.py` | Adaptador único do LLM. Chave vem de `LLM_API_KEY`, provedor configurável e modo de teste com provedor falso |
| `src/extract.py` | Extração com `PROMPT_EXTRACAO_V1` e temperatura 0. Valida o esquema e o `trecho_fonte` literal, com no máximo 1 nova tentativa |
| `src/classify.py` | Interface única que devolve sentimento e probabilidade. O Jev é `NotImplementedError` e o LLM é o caminho normal |
| `src/strategy.py` | `decidir`: COMPRA, VENDA ou MANTER, com motivo (`REGRA_V1`) |
| `src/baselines.py` | Baseline 1 (qualquer notícia positiva) e baseline 2 (sorteio com 1000 simulações e semente fixa) |
| `src/backtest.py` | Execução no próximo pregão, simulação, preços do yfinance com cache, métricas, critério e travas de período |
| `src/explain.py` | Justificativa por operação e relatório diário. O cabeçalho vem da regra e o LLM só descreve |
| `src/auditoria.py` | Log append-only `data/operacoes.jsonl` |
| `src/main.py` | Pipeline retomável. Cada etapa grava em `data/execucoes/AAAA-MM-DD/` |

### Regra de decisão (`REGRA_V1`)

| Situação | Decisão |
|---|---|
| Evento confirmado, positivo, probabilidade **> 0,7**, sem evento negativo do mesmo ticker nos 5 dias anteriores | COMPRA de até 20% do patrimônio |
| Evento confirmado, negativo, probabilidade **> 0,7**, sem evento positivo do mesmo ticker nos 5 dias anteriores | VENDA (zera a posição, se houver) |
| Sem classificação, não confirmado, neutro, probabilidade ≤ 0,7 ou evento oposto recente | MANTER |

### Baselines

1. **Comprar qualquer notícia positiva:** usa os mesmos eventos classificados e a mesma execução, e vende em notícia negativa, mas sem os filtros da regra (confirmação, limiar e evento oposto recente). Isola o valor dos filtros.
2. **Sorteio:** mantém o mesmo número de operações e as mesmas durações da estratégia, com ticker e data de entrada sorteados. Usa 1000 simulações e a semente `20261015`, e devolve a distribuição e a fração de sorteios que empatam com a estratégia ou a superam.
3. **Comprar e segurar o Ibovespa** (`^BVSP`).

## 12. Configuração

1. Python 3.11 ou superior. O projeto foi desenvolvido com Python 3.12.
2. Crie o ambiente e instale as dependências:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows (Linux/macOS: source .venv/bin/activate)
   pip install -r requirements.txt
   ```
3. Chave de API: copie `.env.example` para `.env` e preencha os valores. O `.env` está no `.gitignore`, e a chave **nunca** vai para o código nem para o git.
   ```
   LLM_API_KEY=...
   LLM_PROVEDOR=...   # nome de um provedor registrado com llm.registrar_provedor
   LLM_MODELO=...     # identificador do modelo, registrado em cada saída
   ```
   Nenhum provedor real está implementado ainda (ver Pendências). Para rodar sem LLM real, use o modo de teste.

## 13. Como rodar

| O quê | Comando |
|---|---|
| Testes (sem rede e sem LLM real) | `python -m pytest` |
| Coletar e arquivar notícias uma vez | `python -m src.archive --coletar` |
| Pipeline completo, modo de teste (sem rede, LLM falso, grava em `data/teste/`) | `python -m src.main --teste` ou `QUANT_MODO_TESTE=1 python -m src.main` |
| Pipeline completo, real | `python -m src.main` |
| Backtest | Ainda não pode ser executado: os períodos estão pendentes de aprovação. Depois de aprovados: `backtest.rodar_backtest(eventos, backtest.carregar_precos(inicio, fim), backtest.periodo_do_config("treino"), "noticia")` |

O pipeline pode ser retomado. Se for interrompido, rodar de novo no mesmo dia reaproveita a coleta, a extração, a classificação e as explicações já gravadas, sem novas chamadas ao LLM, e não duplica registros no log de auditoria.

Saídas em `data/` (fora do git):

- `arquivo/AAAA-MM-DD.jsonl`: notícias arquivadas;
- `execucoes/AAAA-MM-DD/`: um arquivo JSON por etapa, mais `relatorio.txt` e `resumo.json`;
- `operacoes.jsonl`: log de auditoria;
- `precos/`: cache de preços, com `downloads.jsonl` registrando a data de cada download.
