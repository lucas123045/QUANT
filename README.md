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

## 5. Data de congelamento da regra

Antes de olhar qualquer resultado do período de teste, a regra é congelada. A partir daí, os itens abaixo não podem mudar:

- `LIMIAR_PROBABILIDADE` (hoje 0,7)
- `MAX_POSICAO_PCT` (hoje 0,20)
- `JANELA_EVENTO_RECENTE_DIAS` (hoje 5), usado pela lógica de `decidir`
- lógica da função `decidir` (`src/strategy.py`, `REGRA_V1`)
- prompt de extração (`PROMPT_EXTRACAO_V1`, `src/extract.py`)
- prompt de classificação (`PROMPT_CLASSIFICACAO_V1`, `src/classify.py`)
- versão do modelo de LLM usado (`LLM_PROVEDOR` e `LLM_MODELO`) e sua data de corte de conhecimento (`DATA_CORTE_CONHECIMENTO_MODELO`)
- esforço do modelo (`ESFORCO = "medium"`, `src/provedores.py`)
- critério de decisão (`CRITERIO_V2`, `ALFA_CRITERIO = 0,05`)
- carteira, aliases e exclusões do casamento de tickers (`src/config.py`)
- semente do baseline 2 (`SEMENTE_BASELINE_2 = 20261015`)
- hash de `requirements.txt` e hash dos preços (`backtest.hash_dos_precos()`)

O código impede rodar o período de teste enquanto `DATA_CONGELAMENTO` for `None`: `periodo_do_config("teste")` levanta `CongelamentoPendente`.

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
  - **Fatos relevantes:** bloqueados até a verificação da CVM (item abaixo).
- [ ] Verificar se a CVM tem histórico utilizável de fatos relevantes para as 5 ações, com data de entrega confiável. O adaptador `coletar_fatos_relevantes` fica como `NotImplementedError` até lá.
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
| `src/news.py` | Coleta RSS (InfoMoney e Money Times) das últimas 24 h, tolerando falhas por fonte. A CVM está bloqueada |
| `src/archive.py` | Arquivo append-only em `data/arquivo/AAAA-MM-DD.jsonl` (data da coleta), com deduplicação por URL |
| `src/llm.py` | Adaptador único do LLM. Chave vem de `LLM_API_KEY`, provedor configurável e modo de teste com provedor falso. Registra o modelo que respondeu e a temperatura efetiva |
| `src/provedores.py` | Provedores reais pelos SDKs oficiais. `openai`: Chat Completions, modelo obrigatório em `LLM_MODELO`, temperatura 0 (repete sem ela se o modelo recusar). `anthropic`: `claude-opus-5-5`, esforço `medium`, fallback do servidor. Recusas tratadas nos dois |
| `src/extract.py` | Extração com `PROMPT_EXTRACAO_V1` (temperatura 0 pedida; null quando o modelo não aceita). Valida o esquema e o `trecho_fonte` literal, com no máximo 1 nova tentativa |
| `src/classify.py` | Interface única que devolve sentimento e probabilidade. O Jev é `NotImplementedError` e o LLM é o caminho normal |
| `src/strategy.py` | `decidir`: COMPRA, VENDA ou MANTER, com motivo (`REGRA_V1`) |
| `src/baselines.py` | Baseline 1 (qualquer notícia positiva) e baseline 2 (sorteio com 1000 simulações e semente fixa) |
| `src/backtest.py` | Execução no próximo pregão, simulação com exposição, preços do yfinance com cache e SHA-256, métricas, `CRITERIO_V2`, aviso de contaminação e travas de período |
| `src/estatistica.py` | Teste t, teste de Welch (distribuição t sem dependências externas), tabela de calibração e escore de Brier |
| `src/funil.py` | Mede o funil notícias → menções → eventos → operações e projeta as operações por semestre |
| `src/avaliacao.py` | Amostras para rotulagem manual; precisão e revocação do casamento e precisão da extração |
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
   LLM_API_KEY=...          # chave da API do provedor escolhido
   LLM_PROVEDOR=openai      # ou anthropic
   LLM_MODELO=...           # obrigatório com openai; com anthropic, padrão claude-opus-5-5
   ```
   Depois de escolher o modelo, registre a data de corte de conhecimento dele em `DATA_CORTE_CONHECIMENTO_MODELO` (seção 5.1), tirada da documentação oficial do provedor.
   Para rodar sem LLM real, use o modo de teste.

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

O pipeline pode ser retomado. Se for interrompido, rodar de novo no mesmo dia reaproveita a coleta, a extração, a classificação e as explicações já gravadas, sem novas chamadas ao LLM, e não duplica registros no log de auditoria. Notícias que já estavam no arquivo sem passar pela IA (por exemplo, coletadas antes pelo botão "Coletar notícias" ou por `archive --coletar`) são extraídas na próxima execução, desde que voltem na coleta; o resumo mostra quantas em `ja_arquivados_sem_extracao`.

Saídas em `data/` (fora do git):

- `arquivo/AAAA-MM-DD.jsonl`: notícias arquivadas;
- `execucoes/AAAA-MM-DD/`: um arquivo JSON por etapa, mais `relatorio.txt` e `resumo.json`;
- `operacoes.jsonl`: log de auditoria;
- `precos/`: cache de preços, com `downloads.jsonl` registrando a data e o SHA-256 de cada download.

### Agendamento e backup

- **Agendamento diário (Windows):** preparado em `scripts\agendar-windows.ps1`, mas inativo até você executá-lo deliberadamente.
- **Backup:** cada execução real cria um ZIP com os dados. O destino prioriza o OneDrive detectado no Windows; `QUANT_BACKUP_DIR` permite escolher outra pasta. Sem OneDrive, um aviso informa se o destino local está no mesmo disco.

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
| Notícias | Arquivo de notícias, com busca, filtro por empresa e "só as que mencionam a carteira" (pelas regras atuais de casamento) |
| Execuções | Cada dia do pipeline: decisões da regra com classificação, trecho da fonte e motivo, e o relatório do dia |
| Operações | Log de auditoria (`operacoes.jsonl`), com motivo, trecho, origem, modelo e explicação |
| Simulação | Carteira com dinheiro fictício e preços reais (ver abaixo) |
| Ações | Coletar notícias, pipeline de teste e pipeline real (pede confirmação, porque tem custo), com o log ao vivo. O backtest aparece bloqueado enquanto os períodos estiverem pendentes |
| Configuração | Parâmetros da regra, do critério, períodos, custos, fontes e aliases. **Somente leitura** |
| Estudos | Guia de economia do zero em 15 lições curtas (fundamentos, ações e risco, como o QUANT testa uma ideia). Cada lição abre com a ideia em uma frase e, quando há dados, mostra o conceito nos números atuais da simulação. Quatro calculadoras (juros compostos, queda e recuperação, retorno real, quantas operações são necessárias) e um glossário. No celular, as lições começam recolhidas e o índice desliza com o dedo, fixo no topo |

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
- A API escuta só em 127.0.0.1.
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
- **Produtos que você está testando:** Estratégia QUANT, Seguir toda notícia e Ibovespa. Cada um mostra rentabilidade, oscilação (baixa < 10%, média < 25%, alta ≥ 25% ao ano), pior queda e % de dias no positivo, e um selo marca o de maior rendimento.
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

A coleta, a IA e a chave continuam só no seu computador. Assim ninguém consegue disparar chamadas pagas ao LLM pelo site, e a chave nunca sai do `.env`. Um teste confere que ela não aparece nos arquivos exportados.

Para atualizar o site, rode o pipeline normalmente (`npm run dev` → Rodar agora) e depois repita os três comandos acima.

Código: `src/web/api.py` (FastAPI), `web/` (React + Vite), `scripts/api.mjs` (sobe a API com o Python da `.venv`).
