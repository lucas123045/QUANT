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

**Versão vigente: `CRITERIO_V2`** (`backtest.avaliar_criterio`), com nível de significância `ALFA_CRITERIO = 0,05`.

A estratégia só é considerada **útil** se, no período de teste e já descontados os custos, cumprir as três condições:

1. **Direção:** o retorno acumulado é maior que o do baseline 1 ("comprar qualquer notícia positiva") **e** maior que o do Ibovespa.
2. **Contra o Ibovespa:** teste t unilateral do **excesso por operação**, com p < 0,05. O excesso de uma operação é o retorno dela menos o retorno do Ibovespa na mesma janela, e t = média ÷ (desvio ÷ √n).
3. **Contra o baseline 1:** teste de Welch unilateral entre os excessos por operação da estratégia e os do baseline 1, com p < 0,05.

Se o teste for indefinido (menos de 2 operações ou variância zero), o resultado é "não demonstrado". Se não superar, o trabalho conclui que **o sinal não foi demonstrado**. Esse é um resultado válido e será reportado como tal.

Controle adicional, que não entra no critério: o baseline 2 (sorteio) dá a fração de sorteios que empatam com a estratégia ou a superam, um p-valor empírico.

> **Por que o critério mudou (V1 → V2, antes de qualquer congelamento).** O `CRITERIO_V1` exigia "diferença de retorno acumulado > erro padrão do retorno médio por operação". Essas grandezas são diferentes. Com sizing de 20%, a diferença cresce com n e o erro padrão cai com √n, então a razão cresce como n^1,5. Com 50 operações de média 0,2% e desvio 3%, o V1 aprovaria com t ≈ 0,5, que não é significativo. O teste `test_criterio_v2_corrige_o_defeito_do_v1` reproduz esse caso.

> Os custos são os configurados em `src/config.py`. Hoje estão zerados (ver seção 8), então o resultado "líquido" é igual ao bruto até que valores de custo sejam aprovados.

> **Limitação do teste de Welch:** as operações da estratégia costumam ser um subconjunto das do baseline 1, então as amostras não são independentes. O teste é aproximado e tende a ser conservador nesse caso.

## 4. Métricas

- **Primária:** retorno acumulado líquido da estratégia contra o Ibovespa no período de teste.
- **Secundárias:**
  - volatilidade (diária e anualizada) e drawdown máximo;
  - retorno anualizado por unidade de volatilidade;
  - exposição média: a fração do patrimônio investida;
  - **Ibovespa com a mesma exposição diária da estratégia**. A estratégia investe no máximo 20% por ação e deixa o resto em caixa, enquanto o Ibovespa comprado e segurado fica 100% investido. Comparar com o Ibovespa na mesma exposição separa a seleção do simples fato de estar mais ou menos investido.
- **Do critério:** excesso médio por operação, estatística t e p-valor (seção 3).
- **De apoio:** número de operações, taxa de acerto e erro padrão do retorno médio por operação.
- **Sensibilidade a custos:** `backtest.sensibilidade_custos(eventos, precos, periodo, tipo_fonte)` repete o backtest com 0%, 0,1%, 0,25% e 0,5% por operação (em cada compra e cada venda) e devolve os retornos e se o critério passa em cada caso. Não muda os custos de `config.py`, que continuam zerados até haver valores aprovados; serve para mostrar se um resultado positivo sobrevive a custos plausíveis.

## 5. Data de congelamento da regra

Antes de olhar qualquer resultado do período de teste, a regra é congelada. A partir daí, os itens abaixo não podem mudar:

- `LIMIAR_PROBABILIDADE` (hoje 0,7)
- `MAX_POSICAO_PCT` (hoje 0,20)
- `JANELA_EVENTO_RECENTE_DIAS` (hoje 5), usado pela lógica de `decidir`
- `MATERIALIDADE_MINIMA` (hoje "media"), `JANELA_REPETICAO_HORAS` (hoje 24) e `HORA_LIMITE_EXECUCAO` (hoje 16h55)
- lógica da função `decidir` (`src/strategy.py`, `REGRA_V3`)
- prompt de extração (`PROMPT_EXTRACAO_V2`, `src/extract.py`)
- prompt de classificação (`PROMPT_CLASSIFICACAO_V2`, `src/classify.py`)
- versão do modelo de LLM usado (`LLM_PROVEDOR` e `LLM_MODELO`) e sua data de corte de conhecimento (`DATA_CORTE_CONHECIMENTO_MODELO`)
- esforço do modelo (`ESFORCO = "medium"`, `src/provedores.py`)
- critério de decisão (`CRITERIO_V2`, `ALFA_CRITERIO = 0,05`)
- carteira, aliases e exclusões do casamento de tickers (`src/config.py`)
- semente do baseline 2 (`SEMENTE_BASELINE_2 = 20261015`)
- hash de `requirements.txt` e hash dos preços (`backtest.hash_dos_precos()`)

O código impede rodar o período de teste enquanto `DATA_CONGELAMENTO` for `None`: `periodo_do_config("teste")` levanta `CongelamentoPendente`.

**Como congelar (`src/congelamento.py`).** `python -m src.congelamento` lista os pré-requisitos, cada um com o que fazer, e mostra a **impressão digital da regra**: o SHA-256 do código de `strategy.py`, dos prompts de extração e de classificação, do casamento de tickers, das fontes e de todos os parâmetros que decidem. Com tudo cumprido, o autor roda `python -m src.congelamento --congelar --confirmo-que-sou-o-autor`, que grava `congelamento.json` na raiz (com a impressão digital, o modelo e os parâmetros) e preenche `DATA_CONGELAMENTO`. A partir daí, cada execução confere a impressão digital e o modelo em uso: se algo mudar, a Visão do sistema avisa que os resultados não valem mais como teste. O mesmo checklist aparece na página Visão do sistema.

Pré-requisitos: modelo com versão datada (`LLM_MODELO`), corte de conhecimento registrado (para o gpt-4.1, a documentação da OpenAI informa 01/06/2024), os três períodos aprovados, validação e teste depois do corte, e o teste começando no futuro (prospectivo).

**Sugestão de períodos (decisão do autor).** Para notícias de portal não há arquivo anterior a 15/10/2026, então o desenho natural é: treino e validação com os fatos relevantes da CVM, todos posteriores ao corte do modelo (por exemplo, treino em 2025 e validação de 01/01/2026 até a data do congelamento, via `src/historico.py`), e teste **prospectivo** a partir do congelamento, com notícias e fatos relevantes, por um prazo fixo (por exemplo, 6 meses).

O teste `test_parametros_congelaveis_nao_foram_alterados` **falha de propósito** se algum parâmetro congelável mudar ou se `DATA_CONGELAMENTO` for preenchida. Atualizá-lo é um ato deliberado, que entra no mesmo commit da mudança aprovada.

| Campo | Valor |
|---|---|
| Data de congelamento | _PENDENTE_ |
| Hash do commit (e tag `regra-congelada-v1`) | _PENDENTE_ |
| Hash dos preços (`hash_dos_precos`) | _PENDENTE_ |
| Hash de `requirements.txt` | _PENDENTE_ |
| Data de corte de conhecimento do modelo | _PENDENTE_ |
| Aprovação | _PENDENTE_ |

Esses campos são preenchidos apenas pelo autor.

## 5.1 Riscos metodológicos (revisão de 2026-10-15)

- **Contaminação por conhecimento do LLM (look-ahead via modelo).** Se o modelo foi treinado com textos posteriores ao início de um período histórico, ele pode "saber" o desfecho ao extrair e classificar eventos daquele período. Nenhum corte temporal do backtest detecta isso.
  - Cada resultado de backtest traz o campo `contaminacao_llm`: `NAO_AVALIADO` enquanto `DATA_CORTE_CONHECIMENTO_MODELO` for `None`; `RISCO` se o período começa antes do corte; `OK` se é inteiramente posterior.
  - Só períodos posteriores ao corte valem como evidência. Isso enfraquece sobretudo o teste de conceito histórico com fatos relevantes da CVM. A validação com notícias arquivadas a partir de agora é menos afetada.
  - A data de corte deve vir da documentação oficial do provedor. Ela não está registrada no repositório e não foi inventada.
- **A probabilidade do LLM não é calibrada.** O valor 0,85 declarado pelo modelo não significa 85% de acerto, então o limiar de 0,7 funciona como um corte de *ranking*, não como uma probabilidade.
  - A calibração deve ser medida no **período de validação** com `estatistica.tabela_calibracao` (faixas e escore de Brier), usando `backtest.acerto_direcional` como desfecho.
  - Se for preciso ajustar o limiar, isso se faz com dados de validação e antes do congelamento.
- **Testes de refutação** (`src/refutacao.py`): `executar(eventos, precos, periodo, tipo_fonte)` reúne placebo (500 embaralhamentos por padrão), defasagens de 0, 1, 2, 5 e 10 pregões e calibração (faixas e Brier). Os três exigem período aprovado; a calibração conta apenas eventos e desfechos dentro do recorte. Execute em treino ou validação. No teste, só depois de congelar a regra. Os resultados são diagnósticos exploratórios: não substituem amostra suficiente nem corrigem viés do LLM.
- **Poder estatístico.** A cadeia de filtros (menção → evento → confirmado → probabilidade > 0,7 → sem evento oposto) reduz muito o número de operações. Antes do teste, o funil deve ser medido com `python -m src.funil`.
  - Primeira medição, em 2026-10-15, com um dia de coleta e sem LLM: 20 notícias, das quais 2 mencionam a carteira (10%). Não é possível estimar operações sem o provedor configurado.
  - O resultado mais provável, com poucas operações, é "sinal não demonstrado", e o trabalho deve ser enquadrado assim desde já.
- **Preços ajustados mudam com o tempo.** O ajuste por proventos (`auto_adjust=True`) é retroativo. O SHA-256 de cada CSV é registrado no download, e o carregamento recusa (`PrecosAlterados`) um cache adulterado ou um novo download diferente do registrado.
- **Qualidade do casamento e da extração não medida.** `python -m src.avaliacao` exporta amostras (semente fixa) para rotular à mão e calcula precisão e revocação do casamento e precisão da extração. Meta: 50 a 100 notícias rotuladas, só com dados de treino ou validação, antes do congelamento.
- **Temperatura.** Com `openai`, a extração pede temperatura 0. Se o modelo não aceitar o parâmetro (alguns modelos de raciocínio), a chamada é repetida sem ele. Os modelos Claude atuais não aceitam parâmetros de amostragem. Em todos os casos, cada saída registra a temperatura de fato aplicada (`0.0` ou `null`) e o modelo que respondeu. A reprodutibilidade vem de outro lado: cada resposta do LLM fica gravada e nunca é pedida de novo.

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
- **Custo da escolha:** a reação intradiária, que costuma ser a parte mais informativa do movimento, fica de fora. A regra é conservadora: pode subestimar o sinal, mas não o inflar com informação futura.
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
  - posições abertas no fim do período são liquidadas teoricamente no último fechamento.
- **Exposição desigual:** a estratégia fica parcialmente em caixa e o Ibovespa, 100% investido. Por isso existem as métricas secundárias de retorno por volatilidade e de Ibovespa com a mesma exposição (seção 4).
- **Contaminação, calibração e poder estatístico:** ver a seção 5.1.
- **Modo de teste:** a saída de `--teste` usa notícias de exemplo e um LLM falso por palavras-chave. O relatório gerado traz um aviso e não pode ser usado em nenhuma conclusão.
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
  - **Fatos relevantes:** coletados da CVM desde 21/10/2026 (`src/cvm.py`).
- [x] Verificar a CVM (21/10/2026): o Portal de Dados Abertos cobre as 5 empresas (filtro por CNPJ), com o PDF de cada fato. Limitações registradas: a data de entrega vem sem hora e o arquivo atrasa alguns dias. Para o teste de conceito histórico, ainda falta decidir se a data sem hora basta.
- [ ] Aprovar datas de treino, validação e teste
- [ ] Definir a data de congelamento da regra
- [ ] Confirmar acesso à API do Jev. Enquanto isso, o LLM é o classificador e `USAR_JEV = False`.
- [x] Implementar provedores reais de LLM: `openai` e `anthropic` (`src/provedores.py`).
- [ ] Configurar a chave (`LLM_API_KEY` no `.env`) e rodar o pipeline real com o LLM. Até lá, a IA só foi exercitada com o provedor falso.
- [ ] Registrar `DATA_CORTE_CONHECIMENTO_MODELO` a partir da documentação oficial do modelo escolhido (seção 5.1).
- [ ] Medir o funil depois de alguns dias de coleta com LLM e estimar o número de operações por período (`python -m src.funil`).
- [ ] Rotular 50 a 100 notícias (dados de validação) e medir o casamento e a extração (`python -m src.avaliacao`).
- [ ] Medir a calibração da probabilidade no período de validação.
- [ ] Aprovar `JANELA_EVENTO_RECENTE_DIAS = 5` e `ALFA_CRITERIO = 0,05` antes de qualquer validação.
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
| `src/news.py` | Coleta RSS das últimas 24 h: feeds gerais e por empresa (tag) do InfoMoney e do Money Times, sem repetir a mesma notícia, tolerando falhas por fonte. Fatos relevantes vêm de `src/cvm.py` |
| `src/archive.py` | Arquivo append-only em `data/arquivo/AAAA-MM-DD.jsonl` (data da coleta), com deduplicação por URL |
| `src/llm.py` | Adaptador único do LLM. Chave vem de `LLM_API_KEY`, provedor configurável e modo de teste com provedor falso. Registra o modelo que respondeu e a temperatura efetiva |
| `src/provedores.py` | Provedores reais pelos SDKs oficiais. `openai`: Chat Completions, modelo obrigatório em `LLM_MODELO`, temperatura 0 (repete sem ela se o modelo recusar). `anthropic`: `claude-opus-5-5`, esforço `medium`, fallback do servidor. Recusas tratadas nos dois |
| `src/extract.py` | Extração com `PROMPT_EXTRACAO_V2` (temperatura 0 pedida; null quando o modelo não aceita). Valida o esquema e o `trecho_fonte` literal, com no máximo 1 nova tentativa |
| `src/classify.py` | Interface única que devolve sentimento e probabilidade. O Jev é `NotImplementedError` e o LLM é o caminho normal |
| `src/strategy.py` | `decidir`: COMPRA, VENDA ou MANTER, com motivo e critérios conferidos (`REGRA_V2`) |
| `src/baselines.py` | Baseline 1 (qualquer notícia positiva) e baseline 2 (sorteio com 1000 simulações e semente fixa) |
| `src/backtest.py` | Execução no próximo pregão, simulação com exposição, preços do yfinance com cache e SHA-256, métricas, `CRITERIO_V2`, aviso de contaminação e travas de período |
| `src/estatistica.py` | Teste t, teste de Welch (distribuição t sem dependências externas), tabela de calibração, escore de Brier, quantil t e intervalo de confiança |
| `src/cvm.py` | Fatos relevantes da CVM (dados abertos IPE, por CNPJ, 1ª versão, texto do PDF) |
| `src/pratica.py` | Carteira prática: as mesmas decisões com custos da B3, IR, caixa no CDI, tamanho pelo risco, limite por setor, saídas e confirmação pela reação do mercado |
| `src/tributacao.py` | IR de ações em operações comuns: 15%, isenção de R$ 20 mil em vendas no mês, compensação de prejuízo, vencimento do DARF |
| `src/surpresa.py` | Surpresa frente à expectativa lida no texto ("acima do consenso", "frustrou"), sem LLM |
| `src/risco.py` | Sharpe e Sortino contra o CDI, beta, maior queda e duração, payoff, fator de lucro, correlações |
| `src/estudo_evento.py` | Estudo de evento (modelo de mercado), calibração da IA e atraso da coleta |
| `src/mercado.py` | Macro do Banco Central, commodities, sinal dos ADRs em Nova York e agenda (Copom, resultados, datas-ex) |
| `src/alertas.py` | Alerta no celular (ntfy ou Telegram) a cada decisão registrada |
| `src/funil.py` | Mede o funil notícias → menções → eventos → operações e projeta as operações por semestre |
| `src/avaliacao.py` | Amostras para rotulagem manual; precisão e revocação do casamento e precisão da extração |
| `src/explain.py` | Justificativa por operação e relatório diário. O cabeçalho vem da regra e o LLM só descreve |
| `src/auditoria.py` | Log append-only `data/operacoes.jsonl` |
| `src/main.py` | Pipeline retomável. Cada etapa grava em `data/execucoes/AAAA-MM-DD/` |

### Regra de decisão (`REGRA_V3`)

| Situação | Decisão |
|---|---|
| Fato sobre a empresa (não só a cotação), confirmado, **relevante** (materialidade média ou alta), **novo** (o mercado ainda não negociou um pregão inteiro com ele), positivo, probabilidade **> 0,7**, **primeira notícia do fato** nas últimas 24 h e sem **fato** negativo confirmado do mesmo ticker nos 5 dias anteriores | COMPRA de até 20% do patrimônio |
| O mesmo, com sentido negativo (sem fato positivo confirmado recente) | VENDA (zera a posição, se houver) |
| Qualquer critério não cumprido | MANTER, com o primeiro critério que falhou como motivo |

**V2 → V3 (21/10/2026, antes do congelamento).** No primeiro dia na nuvem, a V2 registrou 5 compras de PETR4: quatro eram a mesma notícia em dois portais ("a ANP adiou uma audiência pública sobre o Gas Release"), um fato confirmado e positivo, mas sem efeito financeiro mensurável; a quinta era um fato relevante entregue à CVM 8 dias antes. Mudanças:

1. **Materialidade (`PROMPT_CLASSIFICACAO_V2`):** a IA classifica também quanto o fato muda o resultado, o caixa ou o valor da empresa (alta, média ou baixa, com uma frase de motivo e definições objetivas; na dúvida, o nível mais baixo). A regra exige `MATERIALIDADE_MINIMA = "media"`: procedimento, adiamento, agenda, opinião de terceiros e repetição de algo já conhecido ficam de fora.
2. **Fato novo (`HORA_LIMITE_EXECUCAO`):** o evento passa a guardar quando o QUANT soube dele (`timestamp_coleta`). Se isso aconteceu depois do início do leilão de fechamento (16h55) do pregão seguinte ao dia do fato, o mercado já negociou um pregão inteiro com ele, e executar "no pregão seguinte" seria no passado: MANTER. Feriados contam como dia útil (erro conservador).
3. **Repetição (`JANELA_REPETICAO_HORAS = 24`):** notícia da mesma ação, no mesmo sentido, nas 24 h anteriores, que passou por todos os critérios próprios, é a mesma informação: a primeira decide, as outras viram MANTER com o motivo "repetição". A posição por ação já é limitada a 20%, então uma segunda notícia igual não teria o que acrescentar.

Classificações feitas com o prompt V1 não têm materialidade: a V3 não opera sobre elas. As decisões da V2 continuam no log, fora da carteira.

Cada decisão grava a lista de critérios conferidos (`criterios`: cada condição com ✓/✗ e o valor que decidiu). É a justificativa passo a passo que aparece na interface (Carteira › Extrato, Decisões, Análises do dia) e no log de auditoria, junto com a explicação da IA (`PROMPT_EXPLICACAO_V2`, que recebe esses critérios e cita o fato da notícia).

**V1 → V2 (20/10/2026, antes do congelamento; nenhum número mudou).** Nos primeiros dias reais, os 6 eventos extraídos e as 3 operações da V1 vieram de resumos de fechamento ("ações da Petrobras sobem 3%"): o sistema comprava porque o preço já tinha subido, o que é seguir tendência e não reagir à notícia, e esvaziava a hipótese do trabalho. Mudanças:

1. **`PROMPT_EXTRACAO_V2`:**
   - notícia que só relata a variação do preço vira `tipo_evento: "cotacao"`;
   - prévias e projeções de analistas ("deve lucrar mais", "resultado sai dia 29") saem como `confirmado: false`;
   - novos tipos `operacional` (produção, vendas, contratos) e `regulatorio`;
   - o texto enviado ao LLM é limitado a 8.000 caracteres; o trecho continua conferido contra o texto completo.
2. **`REGRA_V2`:**
   - evento `cotacao` → MANTER;
   - o filtro de evento oposto só considera **fatos confirmados**. Na V1, uma prévia de analista bloqueou a venda pelo aumento de capital do Bradesco.
3. **Carteira e log:**
   - a carteira simulada segue só as decisões da regra vigente, a partir do primeiro dia em que ela rodou;
   - as decisões da V1 continuam no log de auditoria, que não é apagado, marcadas como V1;
   - eventos extraídos com o prompt V1 ficam gravados, mas a regra V2 não decide sobre eles nem os usa como histórico.

Validado com o GPT-4.1 real: os 6 resumos de fechamento saíram como `cotacao`, as prévias de balanço como não confirmadas, e fatos como a produção recorde da Petrobras e o aumento de capital do Bradesco como eventos confirmados.

### Baselines

1. **Comprar qualquer notícia positiva:** usa os mesmos eventos classificados e a mesma execução, e vende em notícia negativa, mas sem os filtros da regra (confirmação, limiar e evento oposto recente). Isola o valor dos filtros.
2. **Sorteio:** mantém o mesmo número de operações e as mesmas durações da estratégia, com ticker e data de entrada sorteados. Usa 1000 simulações e a semente `20261015`, e devolve a distribuição e a fração de sorteios que empatam com a estratégia ou a superam.
3. **Comprar e segurar o Ibovespa** (`^BVSP`).

## 12. Instalação em qualquer computador

Baixe o projeto (`git clone` ou o ZIP do GitHub) e rode o instalador. Ele pode ser rodado de novo quando quiser: usa o que já estiver instalado e só completa o que falta.

| Sistema | Instalar | Abrir o QUANT | Ligar/desligar a coleta automática |
|---|---|---|---|
| **Windows** | dois cliques em `instalar.cmd` | dois cliques em `QUANT.cmd` | `agendar.cmd` / `agendar.cmd -Remover` |
| **macOS / Linux** | `bash instalar.sh` | `bash QUANT.sh` | `bash scripts/agendar-unix.sh` / `... --remover` |

O instalador, em 7 passos:

1. **Python 3.11+:** usa o que já existir. No Windows, se faltar, instala o 3.12 pelo `winget`; no macOS/Linux, diz o comando (`brew install python@3.12`, `apt install python3.12 python3.12-venv`).
2. **Node.js 18+:** idem (`winget`, `brew install node` ou nodejs.org).
3. **`.venv` e dependências Python:** recria a `.venv` se ela estiver quebrada, por exemplo depois de copiar a pasta de outro computador.
4. **Dependências do site:** `npm install`. Os atalhos `.cmd` usam `npm.cmd`, então o bloqueio de scripts do PowerShell não atrapalha.
5. **`.env`:** cria a partir do `.env.example` e pergunta a chave do LLM. Pode pular: sem chave, o QUANT continua coletando notícias e só não as analisa.
6. **Testes:** roda os testes automáticos (sem internet e sem custo) para conferir a instalação.
7. **Coleta automática:** oferece ativar no Agendador de Tarefas do Windows ou no `cron` (macOS/Linux).

**Mesmo modelo em todos os computadores.** O `.env.example` já traz `LLM_MODELO=gpt-4.1-2025-04-14`. A versão do modelo é parâmetro da pesquisa (seção 5): trocar de modelo entre computadores muda os resultados. Registre a data de corte de conhecimento dele em `DATA_CORTE_CONHECIMENTO_MODELO` (seção 5.1), tirada da documentação oficial do provedor.

**Instalação manual** (se preferir):

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt      # macOS/Linux: .venv/bin/python -m pip ...
npm install
copy .env.example .env                                      # macOS/Linux: cp .env.example .env
```

O `.env` está no `.gitignore`: a chave **nunca** vai para o código nem para o git. Para rodar sem LLM real, use o modo de teste.

**Vários computadores:** cada um tem sua própria pasta `data/`, que não vai para o git. Para a pesquisa, deixe a coleta automática ligada em **um** computador principal, de preferência um que fique ligado. A vitrine se recusa a publicar a partir de um computador com menos dados que a versão online (seção 14).

## 13. Como rodar

| O quê | Comando |
|---|---|
| Testes (sem rede e sem LLM real) | `python -m pytest` |
| Coletar e arquivar notícias uma vez | `python -m src.archive --coletar` |
| Pipeline completo, modo de teste (sem rede, LLM falso, grava em `data/teste/`) | `python -m src.main --teste` ou `QUANT_MODO_TESTE=1 python -m src.main` |
| Pipeline completo, real | `python -m src.main` |
| Medir o funil | `python -m src.funil` (ou `--data-dir data/teste`) |
| Amostra para rotular o casamento | `python -m src.avaliacao exportar-matching --n 100` e, depois de rotular, `python -m src.avaliacao medir-matching amostra_matching.csv` |
| Amostra para rotular a extração | `python -m src.avaliacao exportar-eventos` e `python -m src.avaliacao medir-extracao amostra_eventos.csv` |
| Hash dos preços (congelamento) | `python -c "from src import backtest; print(backtest.hash_dos_precos())"` |
| Backtest | Ainda não pode ser executado: os períodos estão pendentes de aprovação. Depois de aprovados: `backtest.rodar_backtest(eventos, backtest.carregar_precos(inicio, fim), backtest.periodo_do_config("treino"), "noticia")` |

O pipeline pode ser retomado e rodado várias vezes por dia. Rodar de novo coleta outra vez (sem custo) e soma as notícias novas ao dia; a extração, a classificação e as explicações já gravadas são reaproveitadas, sem novas chamadas ao LLM, e o log de auditoria não duplica registros. Notícias que já estavam no arquivo sem passar pela IA (por exemplo, coletadas antes pelo botão "Coletar notícias" ou por `archive --coletar`) são extraídas na próxima execução, desde que voltem na coleta; o resumo mostra quantas em `ja_arquivados_sem_extracao`.

Saídas em `data/` (fora do git):

- `arquivo/AAAA-MM-DD.jsonl`: notícias arquivadas;
- `execucoes/AAAA-MM-DD/`: um arquivo JSON por etapa, mais `relatorio.txt` e `resumo.json`;
- `operacoes.jsonl`: log de auditoria;
- `precos/`: cache de preços, com `downloads.jsonl` registrando a data e o SHA-256 de cada download.

### Tempo real na nuvem (recomendado)

Um computador pessoal desligado ou dormindo para a coleta: em 16–20/10/2026 houve só 16 coletas em 4 dias, nenhuma em 17 e 18/10. Por isso a coleta oficial roda no **GitHub Actions** (`.github/workflows/quant.yml`), a cada 30 minutos, 24 h por dia, sem nenhum computador ligado:

1. coleta os feeds, arquiva e analisa com o LLM só o que é novo;
2. decide pela regra, registra no log e atualiza a carteira simulada;
3. gera a vitrine e grava tudo no ramo **`dados`** do repositório (cada coleta é um commit: histórico auditável e backup);
4. o site online lê a vitrine desse ramo (`web/.env.production`, `VITE_DADOS_URL`) e se atualiza sem ser republicado.

**Para ligar (uma vez, no GitHub):** Settings › Secrets and variables › Actions › *New repository secret* `LLM_API_KEY` com a chave da OpenAI (em **Repository secrets**, não em Environment secrets). Sem o secret, a nuvem coleta, mas não analisa. Para rodar na hora: aba Actions › *QUANT* › *Run workflow*. A nuvem também roda sozinha quando chega código novo na `main`.

**Agendador externo (recomendado).** O agendamento do GitHub atrasa ou pula execuções: em 21/10/2026, o "a cada 30 minutos" rodou 2 vezes em 9 horas, e a notícia chegava ao QUANT, em mediana, 2 horas depois de publicada. Para manter os 30 minutos:

1. no Vercel (Settings › Environment Variables), crie `QUANT_CRON_SEGREDO` (um segredo longo) e `QUANT_GITHUB_TOKEN` (token do GitHub com permissão *Actions: Read and write* no repositório) e faça *Redeploy*;
2. no [cron-job.org](https://cron-job.org) (gratuito), crie uma tarefa a cada 30 minutos chamando `https://SEU-SITE.vercel.app/api/nuvem?agendar=SEU_SEGREDO`.

O endereço nunca empilha execuções (se já houver uma na fila, não dispara outra) e recusa segredo errado. A Visão do sistema avisa quando a coleta passa mais de 90 minutos sem rodar.

### Estudo histórico com os fatos relevantes da CVM

`python -m src.historico --desde 2025-01-01` processa todos os fatos relevantes da carteira **e de um universo ampliado** (`UNIVERSO_ESTUDO`: 19 grandes empresas do Ibovespa, de setores variados, com o mesmo código de negociação desde junho de 2024, critério definido antes de olhar qualquer retorno) entregues à CVM a partir da data, que precisa ser posterior ao corte de conhecimento do modelo: a IA não conhece o desfecho. Cada fato entra como se tivesse sido coletado no dia da entrega, e a extração, a classificação e a regra vigente rodam dia a dia, em ordem, só com o histórico anterior. Os dados ficam em `data/historico/` (separados da carteira) e o resultado aparece em Evidências › Histórico. `--estimar` conta os fatos e estima o custo antes de chamar a IA (372 fatos de 2025 a 21/10/2026: cerca de US$ 3,50).

Por que o universo ampliado: com as 5 ações da carteira, os fatos relevantes rendem 10 a 15 eventos independentes por ano, e detectar um efeito de 1% em 5 pregões (desvio do retorno anormal de ~3,8%) pede ~110. A carteira ao vivo não muda: o universo vale só para o estudo.

**No computador:** com a nuvem ligada, o PC não deve coletar também, senão haveria dois conjuntos de dados. Rode `agendar.cmd -Sincronizar` (Windows) ou `bash scripts/agendar-unix.sh 30 --sincronizar` (macOS/Linux): o PC passa a só trazer os dados da nuvem para `data/` (`python -m src.sincronizar`), juntando sem perder nada local. O `QUANT.cmd`/`QUANT.sh` também sincroniza ao abrir.

### Funcionamento automático, agendamento e backup

O pipeline pode rodar várias vezes por dia. Cada execução coleta de novo, soma ao que já foi coletado no dia e só manda para o LLM o que é novo; sem notícia nova, não há nenhuma chamada paga (nem o resumo do relatório, que só é refeito quando as decisões mudam). Uma trava (`data/.pipeline.lock`) impede duas execuções ao mesmo tempo, por exemplo o agendamento e o botão da interface.

**Por que coletar com frequência:** os feeds RSS mostram só as 10 notícias mais recentes. Medido em 16/10/2026, isso cobria cerca de 1,2 hora no InfoMoney e 3 horas no Money Times. Coletando uma vez por dia, a maior parte das notícias se perderia.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1                       # pipeline a cada 30 min + vitrine às 20h
powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -IntervaloMinutos 60  # a cada hora
powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -SoColeta             # só coleta, sem LLM e sem custo
powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -Publicar             # a vitrine diária também faz git push
powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -Remover              # desfaz
```

- **Tarefas criadas:** "QUANT - coleta automatica" (a cada 30 min, sem fim) e "QUANT - vitrine diaria" (20h). Rodam pelo `pythonw.exe`, sem abrir janela, via `python -m src.agendado pipeline|coleta|vitrine`. Se o computador estiver desligado ou dormindo, a tarefa roda quando ele voltar.
- **Log:** `data/agendamento.log`, em UTF-8, com início, resumo e fim de cada execução (e o erro completo, se houver). Ao passar de 5 MB, vira `agendamento.log.old`.
- **Na interface:** a página Notícias mostra a hora da última coleta e quantas notícias novas ela trouxe, recarrega sozinha a cada 5 minutos e avisa se a coleta automática parecer parada (mais de 3 horas sem coletar).
- **Certificados:** o InfoMoney serve a cadeia de certificados incompleta, que o Python sozinho recusa. Os downloads usam a verificação do sistema operacional (`truststore`, em `src/rede.py`), que continua recusando certificado inválido.
- **Backup:** cada execução real pode criar um ZIP com os dados, mas no máximo um a cada 6 horas. O destino prioriza o OneDrive detectado no Windows; `QUANT_BACKUP_DIR` permite escolher outra pasta. Sem OneDrive, um aviso informa se o destino local está no mesmo disco.

## 14. Interface web

Interface local para acompanhar o projeto e disparar as ações, sem usar a linha de comando.

**Pré-requisitos:** a `.venv` com `pip install -r requirements.txt` e o Node.js 18 ou superior.

```powershell
npm install      # só na primeira vez
npm run dev      # sobe a API (porta 8000) e o site (porta 5173) e abre o navegador
```

Para parar, aperte Ctrl+C no terminal. O endereço é http://127.0.0.1:5173. A documentação interativa da API fica em http://127.0.0.1:5173/api/docs.

| Página | O que mostra |
|---|---|
| Painel | Provedor e modelo do LLM, se a chave está configurada (a chave nunca é exibida), status de períodos, congelamento e corte do modelo, funil, última execução, carteira e pendências |
| Notícias | Arquivo de notícias, com busca, filtro por empresa e "só as que mencionam a carteira" (pelas regras atuais de casamento). Mostra 100 por vez, com "Mostrar mais" |
| Execuções | Cada dia do pipeline: decisões da regra com classificação, trecho da fonte e motivo, e o relatório do dia |
| Operações | Log de auditoria (`operacoes.jsonl`), com motivo, trecho, origem, modelo e explicação |
| Simulação | Carteira com dinheiro fictício e preços reais (ver abaixo) |
| Ações | Coletar notícias, pipeline de teste e pipeline real (pede confirmação, porque tem custo), com o log ao vivo. O backtest aparece bloqueado enquanto os períodos estiverem pendentes |
| Configuração | Parâmetros da regra, do critério, períodos, custos, fontes e aliases. **Somente leitura** |
| Estudos | Guia de economia do zero em três abas. **Lições:** 15 lições curtas em três partes (fundamentos, ações e risco, como o QUANT testa uma ideia), em lista sanfonada; cada uma abre com a ideia em uma frase e, quando há dados, mostra o conceito nos números atuais da simulação, que ficam numa lateral fixa no computador. **Calculadoras:** juros compostos, queda e recuperação, retorno real e quantas operações são necessárias. **Glossário:** 16 termos. A aba escolhida é lembrada |

Visual de painel de banco/fintech nas cores do projeto (grafite e âmbar):
- barra lateral com ícones e cartões arredondados;
- saldo em destaque e gráficos com curvas suaves;
- escuro por padrão, com tema claro (tom de papel) na barra lateral;
- fontes IBM Plex incluídas no projeto, sem depender de internet.

A página inicial é **Minha carteira** (a simulação). Ao entrar, uma tela de abertura mostra o logo e o nome, com animação curta. Ela fica no próprio `index.html`, para aparecer antes de o JavaScript carregar, e some quando os primeiros dados chegam: no mínimo 1,2 s e no máximo 6 s. Para quem pede menos movimento no sistema, a animação é desligada.

**No celular** o visual é de app de banco:
- **Navegação:** barra fixa embaixo (Carteira, Notícias, Análises, Decisões e Mais, que abre o menu completo).
- **Saldo:** cartão único com investido, caixa e rendimento embutidos.
- **Atalhos redondos:** Estudos, Sistema, Rodar e Regras (o que não cabe na barra de baixo).
- **Gráfico do patrimônio:** versão compacta, com eixo em "R$ 100 mil" e cursor que segue o dedo.
- **Carrosséis de deslizar:** ações, produtos e "Como funciona".
- **Decisões em cartões:** em vez de tabela, cada decisão vira um cartão com a previsão da IA, a decisão e o motivo.
- **Botão voltar:** o do celular funciona entre as telas.

Conferido com emulação de iPhone (390 px), sem rolagem lateral. O site também pode ser **instalado como app**, com manifesto e ícones:
- **Android (Chrome):** menu ⋮ → "Adicionar à tela inicial" / "Instalar app".
- **iPhone (Safari):** compartilhar → "Adicionar à Tela de Início".

O app abre em tela cheia, sem a barra do navegador. Quando um arquivo `.py` em `src/` muda, a API reinicia sozinha.

O seletor "Dados: Reais / Teste", na barra lateral, alterna entre `data/` e `data/teste/`. No modo de teste aparece uma faixa avisando que nada dali serve para conclusões.

**Garantias:**
- A API escuta só em 127.0.0.1 e recusa pedidos com outro nome de host (proteção contra DNS rebinding).
- Ela não altera nenhum parâmetro congelável.
- Ela não devolve a chave de API.
- Ela roda uma ação por vez.

### Simulação (paper trading)

A aba **Simulação** mantém uma carteira fictícia de R$ 100.000 (`CAPITAL_INICIAL`) que segue, daqui para frente, as compras e vendas do log de auditoria. Essas decisões são da regra, não do LLM.

- **Execução:** como no backtest, no fechamento do primeiro pregão posterior ao dia da notícia, com até 20% do patrimônio por ação e os custos de `config.py`.
- **Preços:** fechamentos reais do Yahoo Finance, ajustados por proventos. São salvos em `data/simulacao/precos/`, um download por dia. Antes das 18h30 (horário de São Paulo), o preço do dia é considerado parcial: não é pedido nem gravado no cache.

A aba tem a forma de um painel de banco:

- **Saldo total** em destaque, com variação desde o início, cartões de investido, caixa e rendimento das posições, e um botão para esconder os valores.
- **Maturidade da simulação:** selo "muito cedo / histórico curto / histórico razoável", com barras de progresso de dias de pregão (meta de 126) e de decisões (meta de 30). Serve para que ninguém conclua "é seguro" com poucas semanas de dados fictícios.
- **Produtos que você está testando:** Estratégia QUANT, Seguir toda notícia, Ibovespa e Renda fixa (CDI). Cada um mostra rentabilidade, oscilação (baixa < 10%, média < 25%, alta ≥ 25% ao ano), pior queda e % de dias no positivo, e um selo marca o de maior rendimento.
- **Renda fixa (CDI):** o mesmo capital aplicado a 100% do CDI desde o primeiro pregão, sem impostos nem taxas (série 12 do SGS do Banco Central, com cache em `data/simulacao/cdi/`). Mostra o custo de oportunidade do caixa, que na simulação rende 0%. É só comparação: não entra na regra nem no critério estatístico. Se o Banco Central não responder, a carteira aparece sem esse produto e com um aviso.
- **E com custos?** Abaixo dos produtos, o rendimento que a estratégia teria com 0,1%, 0,25% e 0,5% de custo por operação.
- **Onde está o dinheiro:** rosca de alocação por ação e caixa.
- **Evolução do patrimônio:** estratégia, baseline 1 e Ibovespa, com filtro Semana, Mês ou Tudo e cursor.
- **Seus ativos:** um cartão por ação, com preço real, variação no dia, gráfico de 30 dias e situação (na carteira, compra agendada, venda agendada ou sem posição). O cartão mostra também a posição e o rendimento, e a última notícia analisada: o que a IA classificou, o que a regra decidiu e por quê.
- **Rendimento de cada decisão:** barras para cima (ganho) ou para baixo (perda), com a calculadora "E se eu tivesse aplicado R$ X".
- **Histórico da regra:** decisões executadas, rendimento médio, acertos, melhor e pior, e a margem de incerteza da média.
- **Próximas movimentações** e **extrato**, como num banco, além das ordens não executadas com o motivo.
- **Como funciona:** a explicação passo a passo, incluindo por que não existe "quanto vai render".

**Não há previsão de rendimento.** Ninguém sabe quanto uma ação vai render, e mostrar um número desses seria inventá-lo. A aba mostra o que já aconteceu e a incerteza disso.

É uma **validação prospectiva**: cada decisão é registrada antes de o resultado existir, então não há como ajustar nada olhando o futuro, e não há contaminação pelo conhecimento do LLM. **Enquanto a regra não for congelada, o resultado é exploratório** e não substitui o período de teste. Não é recomendação de investimento.

Código: `src/simulacao.py`, `GET /api/simulacao`, `web/src/paginas/Simulacao.jsx` e `web/src/GraficoPatrimonio.jsx`. As cores das três séries foram validadas para daltonismo e contraste nos dois temas.

### Na prática, Evidências e Mercado (camada prática, fora da pesquisa)

Três páginas para quem quer usar o QUANT como apoio a decisões reais. **Nenhuma altera a regra congelada nem o critério do trabalho**: a carteira da pesquisa continua igual.

**Na prática** (`src/pratica.py`, `GET /api/pratica`): as mesmas decisões da regra, operadas como um investidor operaria.

| O que muda | Como | Por quê |
|---|---|---|
| **Portão de evidência** | Só compra quando os eventos **anteriores** (com os 5 pregões depois da execução já encerrados) somam 30 ou mais e o limite inferior do intervalo unilateral de 90% do retorno anormal médio supera o custo de ida e volta. Sem isso, o dinheiro fica no CDI | Testar uma hipótese (carteira da pesquisa, que opera sempre) é diferente de investir nela: o investidor só arrisca depois de evidência, e o pior caso vira o CDI |
| Custos | 0,032% por lado: tarifa da B3 no leilão de fechamento (negociação 0,007% + CCP 0,0224% + TTA 0,0026%, tabela da B3 consultada em 21/10/2026); corretagem zero | Custo zero superestima o resultado |
| Imposto de renda | 15% sobre o lucro do mês; isento se as vendas do mês não passam de R$ 20 mil (isenção "tudo ou nada"); prejuízo compensado depois (`src/tributacao.py`). A MP 1.303/2025, que mudaria isso, caducou em 08/10/2025 | Com posições de R$ 20 mil, quase toda venda é tributável |
| Caixa | Rende 100% do CDI | Dinheiro parado no Brasil rende ~14% ao ano |
| Tamanho | Até 20%, menos para ações que oscilam mais que 25% ao ano | Cada posição pesa o mesmo risco |
| Setor | No máximo 30% por setor | Itaú e Bradesco têm correlação ~0,9: são quase a mesma aposta |
| Saída | 20 pregões, ou antes se a perda passar de 2 desvios do esperado no período | A regra só vende com notícia negativa: na prática, seguraria para sempre |
| Reação do mercado | Não compra se, antes da execução, a ação já reagiu com força **contra** a notícia (\|z\| > 2 além do Ibovespa) | O mercado leu como surpresa ruim. Reação forte **a favor** não barra: movimentos causados por notícia tendem a continuar (Chan, 2003) |
| Surpresa no texto | Não compra se o texto diz que o número veio abaixo do esperado (`src/surpresa.py`, palavras-chave, sem LLM) | O que move o preço é a notícia comparada à expectativa |

Cada compra traz as checagens passo a passo, e cada decisão que a prática não seguiu traz o motivo. A página mostra também Sharpe e Sortino contra o CDI, beta, maior queda e sua duração, payoff e fator de lucro (`src/risco.py`; anualizados só com 60 pregões ou mais), e a correlação entre as ações.

**Evidências** (`src/estudo_evento.py`, `GET /api/evidencias`): estudo de evento com retorno anormal pelo modelo de mercado (beta estimado nos 120 pregões anteriores). Mede o que a ação já tinha andado **antes da execução** e o que sobrou **depois** (1, 5 e 20 pregões), por grupo (operados, confirmados, tipo de evento, fonte, reação), com intervalo de 95% pela t de Student. O mesmo fato em vários portais conta uma vez. Mostra também a calibração da confiança da IA (taxa de acerto por faixa e escore de Brier) e o atraso da coleta por portal. Com menos de 10 eventos, a página diz que não dá para concluir.

**Mercado** (`src/mercado.py`, `GET /api/mercado`): Selic (desde quando), IPCA 12 meses, juro real, dólar, Brent e minério de ferro; o **sinal de Nova York** (variação implícita para cada ação desde o último negócio na B3: (1 + ADR) × (1 + dólar) − 1, com os ADRs PBR-A, VALE, ITUB, BBD e ABEV, inclusive pré e pós-mercado); e a agenda (Copom 2026, resultados e datas-ex do Yahoo, a conferir no RI).

**Fatos relevantes da CVM** (`src/cvm.py`): entram na coleta pelo Portal de Dados Abertos da CVM (documentos IPE), filtrados por CNPJ, só a primeira versão de cada documento, com o texto do PDF. A data de entrega vem sem hora (registrada como 23h59) e o arquivo atrasa alguns dias. Seguem a regra com `tipo_fonte = "fato_relevante"` e não se misturam à carteira, que é de notícias de portal.

**Alertas no celular** (`src/alertas.py`): a cada compra ou venda registrada, uma notificação com o motivo e os critérios, por ntfy (sem cadastro) ou Telegram. Configuração no `.env` (veja `.env.example`) ou nos segredos do GitHub.

### Versão online (vitrine somente leitura)

O site publicado (ex.: Vercel) **não tem a API Python**. Ele mostra uma "fotografia" dos dados, gerada no seu computador:

```powershell
npm run vitrine                      # gera web/public/dados/ a partir de data/
git add web/public/dados
git commit -m "Atualiza vitrine"
git push                             # o Vercel republica sozinho
```

Na versão publicada:
- todas as páginas funcionam em modo leitura, com a faixa "Versão online, somente leitura" e a data dos dados;
- os botões de "Rodar agora" ficam desativados.

**Proteção contra apagar o site sem querer:** a vitrine é gerada numa pasta temporária e só substitui a publicada no fim. Como o arquivo de notícias e o log de operações só crescem, se a nova tiver menos notícias ou operações que a publicada (por exemplo, rodando num computador com `data/` vazia), o comando recusa e explica o motivo. Para publicar mesmo assim: `npm run vitrine -- --forcar`.

A coleta, a IA e a chave continuam só no seu computador. Assim ninguém consegue disparar chamadas pagas ao LLM pelo site, e a chave nunca sai do `.env`. Um teste confere que ela não aparece nos arquivos exportados.

Para atualizar o site, rode o pipeline normalmente (`npm run dev` → Rodar agora) e depois repita os três comandos acima.

Código: `src/web/api.py` (FastAPI), `web/` (React + Vite), `scripts/api.mjs` (sobe a API com o Python da `.venv`).
