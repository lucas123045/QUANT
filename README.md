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

- `LIMIAR_PROBABILIDADE`
- `MAX_POSICAO_PCT`
- lógica da função `decidir` (`src/strategy.py`)
- prompt de extração (`PROMPT_EXTRACAO_V1`, `src/extract.py`)
- versão do modelo de LLM usado

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
- Fins de semana e feriados da B3: o evento entra no próximo pregão com negociação.
- _Pendente de definição:_
  - o horário de fechamento usado como corte, já que a B3 muda o horário do pregão ao longo do ano;
  - o tratamento de eventos publicados **durante** o pregão.

## 8. Escopo e limitações

- **Não é tempo real:** é um pipeline diário, em lote. _Pendente de confirmação com o professor._
- **Custos zerados:** corretagem, emolumentos e slippage estão em zero por padrão, como parâmetros explícitos em `src/config.py`. Nenhum valor foi inventado.
- **Impostos não modelados:** não há alíquotas no modelo sem verificação com um contador.
- **Viés de sobrevivência:** a carteira foi escolhida hoje, com conhecimento de quais empresas continuam grandes e listadas. Isso tende a favorecer os resultados históricos.
- **Poder estatístico baixo:** com poucas operações, o erro padrão é grande e diferenças pequenas não são distinguíveis de ruído.

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

- [ ] Arquivar notícias e fatos relevantes com timestamp e fonte (**prioridade 1**). Início do arquivamento: _[data a definir]_
- [ ] Verificar se a CVM tem histórico utilizável de fatos relevantes para as 5 ações, com data de entrega confiável
- [ ] Aprovar datas de treino, validação e teste
- [ ] Definir a data de congelamento da regra
- [ ] Confirmar acesso à API do Jev
- [ ] Confirmar "tempo real" com o professor
- [ ] Confirmar a carteira
- [ ] Verificar aspectos tributários com contador (não modelar alíquotas sem verificação)
