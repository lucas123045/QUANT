import { useState } from "react";
import { useApi } from "../api.js";
import { Cartao } from "../ui.jsx";
import Icone from "../icones.jsx";

const finito = (n) => n != null && Number.isFinite(Number(n));
const dinheiro = (n) => (finito(n)
  ? Number(n).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "—");
const percentual = (n, casas = 1, sinal = false) => {
  if (!finito(n)) return "—";
  const v = Number(n) * 100;
  return `${sinal && v > 0 ? "+" : ""}${v.toLocaleString("pt-BR", { maximumFractionDigits: casas })}%`;
};
const numero = (texto, padrao = 0) => (finito(texto) ? Number(texto) : padrao);
const limitar = (v, min, max) => Math.min(max, Math.max(min, v));

/* ------------------------------------------------------------------ lições
   Cada lição: título, a ideia "em uma frase", o texto, uma fórmula opcional e,
   quando há dados, o mesmo conceito aplicado aos números atuais da simulação. */

const MODULOS = [
  { id: "fundamentos", titulo: "Fundamentos do dinheiro", texto: "Retorno, juros, inflação e a renda fixa como ponto de partida." },
  { id: "risco", titulo: "Ações e risco", texto: "O que se compra na bolsa e como medir o quanto um investimento balança." },
  { id: "metodo", titulo: "Como o QUANT testa uma ideia", texto: "Por que o sistema compara, desconfia e exige muitos casos antes de concluir." },
];

const LICOES = [
  {
    id: "retorno", modulo: "fundamentos", titulo: "Retorno",
    frase: "Quanto o dinheiro mudou em relação ao começo, em porcentagem.",
    corpo: <>
      <p><strong>Capital</strong> é o valor inicial. <strong>Retorno</strong> mede a variação sobre ele: se R$ 100.000 viram R$ 105.000, o retorno é de 5%.</p>
      <p>Sozinho, o retorno não diz em quanto tempo isso aconteceu, nem desconta inflação, custos ou impostos. Um ganho de 5% em um mês e 5% em dois anos são resultados muito diferentes.</p>
    </>,
    formula: "retorno = (valor final ÷ valor inicial) − 1",
    noQuant: ({ est, capital }) => est && <>A carteira começou com {dinheiro(capital)} fictícios e está em {dinheiro(est.patrimonio)}: retorno de {percentual(est.retorno_acumulado, 2, true)} no período.</>,
  },
  {
    id: "juros", modulo: "fundamentos", titulo: "Juros compostos",
    frase: "O rendimento passa a render também — o crescimento acelera com o tempo.",
    corpo: <>
      <p>Quando o ganho fica aplicado, o mês seguinte rende sobre o valor original <em>e</em> sobre os ganhos anteriores. Com taxa constante, o saldo é multiplicado por <code>(1 + taxa)</code> a cada período.</p>
      <p>Por isso taxas mensais pequenas viram números grandes em prazos longos: 1% ao mês dá cerca de 12,7% ao ano, não 12%. Ações, porém, não pagam taxa fixa; a calculadora mostra só a matemática de uma hipótese.</p>
    </>,
    formula: "valor final = valor inicial × (1 + taxa)^períodos",
  },
  {
    id: "inflacao", modulo: "fundamentos", titulo: "Inflação e retorno real",
    frase: "Ganhar 10% com inflação de 6% aumenta o poder de compra só em cerca de 3,8%.",
    corpo: <>
      <p>A inflação reduz o que o dinheiro compra. No Brasil, o índice oficial é o IPCA, medido pelo IBGE. O <strong>retorno real</strong> é o ganho depois de descontar a inflação do mesmo período.</p>
      <p>Subtrair (10% − 6% = 4%) é só uma aproximação; o cálculo exato divide os fatores. A diferença cresce quando as taxas são altas.</p>
    </>,
    formula: "retorno real = (1 + retorno) ÷ (1 + inflação) − 1",
  },
  {
    id: "cdi", modulo: "fundamentos", titulo: "CDI e o custo de oportunidade",
    frase: "Dinheiro parado não é neutro: ele deixa de render o que a renda fixa pagaria.",
    corpo: <>
      <p>A <strong>Selic</strong> é a taxa básica de juros definida pelo Banco Central. O <strong>CDI</strong> acompanha a Selic de perto e é a referência da maior parte da renda fixa (CDBs, fundos DI, Tesouro Selic).</p>
      <p><strong>Custo de oportunidade</strong> é o que você deixa de ganhar pela alternativa que não escolheu. Para quem investe em ações no Brasil, a alternativa óbvia é a renda fixa: uma estratégia só vale a pena se compensar esse rendimento e o risco a mais.</p>
    </>,
    noQuant: ({ caixaPct, est, d }) => {
      const rf = d?.carteiras?.cdi;
      const caixa = `Na simulação, o dinheiro em caixa rende 0%${finito(caixaPct) ? ` — e hoje ${percentual(caixaPct, 0)} da carteira está em caixa` : ""}.`;
      if (!rf || !est) return <>{caixa} Na vida real esse valor poderia render perto do CDI.</>;
      return <>{caixa} No mesmo período, tudo no CDI teria rendido {percentual(rf.retorno_acumulado, 2, true)}, contra {percentual(est.retorno_acumulado, 2, true)} da estratégia. É por isso que a Carteira mostra a renda fixa como um dos produtos.</>;
    },
  },
  {
    id: "acoes", modulo: "risco", titulo: "Ações e proventos",
    frase: "Uma ação é um pedaço de uma empresa; o preço reflete expectativas, não garantias.",
    corpo: <>
      <p>Quem compra uma ação vira sócio de uma fração da empresa. O preço muda com resultados, juros, câmbio, política e, principalmente, com o que o mercado <em>espera</em> que vá acontecer. Uma notícia boa que todos já esperavam pode não mover o preço.</p>
      <p><strong>Proventos</strong> (dividendos e juros sobre capital próprio) são parte do lucro distribuída aos acionistas. Os preços usados aqui são <strong>ajustados por proventos</strong>, para que o pagamento não pareça uma queda.</p>
    </>,
    noQuant: ({ d }) => d?.ativos?.length > 0 && <>O QUANT acompanha {d.ativos.length} ações: {d.ativos.map((a) => `${a.empresa} (${a.ticker})`).join(", ")}. A escolha foi feita hoje, sabendo que essas empresas continuam grandes — isso favorece o passado (viés de sobrevivência).</>,
  },
  {
    id: "ibovespa", modulo: "risco", titulo: "Ibovespa e benchmark",
    frase: "Benchmark é a régua: um resultado só é bom ou ruim comparado a uma alternativa.",
    corpo: <>
      <p>O <strong>Ibovespa</strong> é o principal índice da B3: uma carteira teórica das ações mais negociadas, revisada a cada quatro meses. Comprar o índice e esperar é a forma mais simples de "investir na bolsa".</p>
      <p>Se uma estratégia ganha 8% enquanto o índice ganha 12%, ela perdeu para a alternativa mais simples, mesmo tendo lucro. A comparação só é justa no mesmo período e com o mesmo capital.</p>
    </>,
    noQuant: ({ est, ibov }) => est && ibov && <>No mesmo período, a estratégia fez {percentual(est.retorno_acumulado, 2, true)} e o Ibovespa, {percentual(ibov.retorno_acumulado, 2, true)}.</>,
  },
  {
    id: "volatilidade", modulo: "risco", titulo: "Oscilação (volatilidade)",
    frase: "Mede o quanto o valor sobe e desce no dia a dia — não para que lado vai.",
    corpo: <>
      <p>A volatilidade é o desvio padrão dos retornos diários. Para comparar com números anuais, o sistema multiplica pela raiz de 252, o número aproximado de pregões em um ano.</p>
      <p>Referência: o Ibovespa costuma oscilar em torno de 20% a 25% ao ano. Oscilação baixa não elimina perdas; só indica que o caminho foi menos acidentado.</p>
    </>,
    formula: "volatilidade anualizada = desvio padrão diário × √252",
    noQuant: ({ est, ibov }) => est && ibov && finito(est.volatilidade_anualizada) && <>Oscilação anualizada até agora: estratégia {percentual(est.volatilidade_anualizada)}, Ibovespa {percentual(ibov.volatilidade_anualizada)}. Com poucos dias, essa estimativa ainda é instável.</>,
  },
  {
    id: "drawdown", modulo: "risco", titulo: "Queda máxima (drawdown)",
    frase: "A pior queda do pico até o fundo — e perdas pedem altas maiores para voltar.",
    corpo: <>
      <p>O <strong>drawdown</strong> compara o patrimônio de cada dia com o maior valor já atingido antes. A queda máxima é o pior desses recuos no período.</p>
      <p>A recuperação é assimétrica: depois de cair 20%, o ganho incide sobre um saldo menor, então é preciso subir 25% para voltar. Uma queda de 50% exige alta de 100%.</p>
    </>,
    formula: "alta necessária = 1 ÷ (1 − queda) − 1",
    noQuant: ({ est, ibov }) => est && ibov && <>Maior queda até agora: estratégia {percentual(est.drawdown_maximo, 2)}, Ibovespa {percentual(ibov.drawdown_maximo, 2)}.</>,
  },
  {
    id: "exposicao", modulo: "risco", titulo: "Exposição: quanto está investido",
    frase: "Menos dinheiro na bolsa significa menos oscilação — não necessariamente mais habilidade.",
    corpo: <>
      <p><strong>Exposição</strong> é a parte do patrimônio aplicada em ações; o resto fica em caixa. Um colchão também não oscila, e nem por isso é um bom investimento.</p>
      <p>Por isso o projeto calcula também o Ibovespa "com a mesma exposição" da estratégia: assim dá para separar o efeito de escolher bem as ações do simples efeito de estar menos investido.</p>
    </>,
    noQuant: ({ d, est }) => <>A regra investe até {percentual(d?.parametros?.max_posicao_pct ?? 0.2, 0)} do patrimônio por ação{est && finito(est.exposicao_media) ? `; em média, a estratégia ficou ${percentual(est.exposicao_media)} investida, contra 100% do Ibovespa` : ""}.</>,
  },
  {
    id: "regra", modulo: "metodo", titulo: "Da notícia à decisão",
    frase: "A IA lê e resume; quem decide comprar ou vender é uma regra fixa.",
    corpo: <>
      <p>O fluxo tem etapas separadas: os portais são lidos, a IA identifica o evento (tipo, impacto, se foi confirmado) e copia o trecho que o comprova, e outra chamada estima se o efeito tende a ser positivo ou negativo.</p>
      <p>A decisão vem de uma <strong>regra determinística</strong>: mesma entrada, mesma saída, sem opinião da IA. Isso permite auditar cada operação e garante que o teste mede a regra, não o humor do modelo.</p>
    </>,
    noQuant: ({ d }) => {
      const p = d?.parametros;
      return p && <>Compra quando o evento é confirmado, positivo, com confiança acima de {p.limiar_probabilidade.toLocaleString("pt-BR")} e sem notícia negativa da mesma empresa nos {p.janela_evento_recente_dias} dias anteriores. A venda é o espelho disso.</>;
    },
  },
  {
    id: "futuro", modulo: "metodo", titulo: "Não olhar o futuro",
    frase: "Um teste só vale se usar apenas o que se sabia no momento da decisão.",
    corpo: <>
      <p><strong>Look-ahead</strong> é usar, sem perceber, uma informação que ainda não existia. Exemplo: comprar no fechamento do dia de uma notícia publicada às 14h — o preço de fechamento já pode refletir a notícia.</p>
      <p>Por isso o QUANT executa toda notícia do dia D no fechamento do <em>primeiro pregão depois de D</em>. É conservador: perde a reação do próprio dia, mas não infla o resultado. Outro risco é o próprio modelo de IA ter sido treinado com textos que já contam o desfecho; por isso o projeto registra a data de corte de conhecimento do modelo.</p>
    </>,
    noQuant: ({ d }) => d?.pendentes?.length > 0 && <>{d.pendentes.length === 1 ? "Há 1 movimentação aguardando o próximo pregão para ser executada." : `Há ${d.pendentes.length} movimentações aguardando o próximo pregão para serem executadas.`}</>,
  },
  {
    id: "comparacao", modulo: "metodo", titulo: "Comparar com alternativas simples",
    frase: "Se uma ideia simples faz o mesmo, os filtros da regra não acrescentam nada.",
    corpo: <>
      <p>O QUANT compara a regra com três alternativas, chamadas de <strong>baselines</strong>:</p>
      <ul>
        <li><strong>Seguir toda notícia:</strong> compra em qualquer notícia positiva, sem os filtros. Mostra se os filtros ajudam.</li>
        <li><strong>Sorteio:</strong> mesmo número de operações e mesmas durações, com ações e datas sorteadas mil vezes. Mostra quanto se ganharia por acaso.</li>
        <li><strong>Ibovespa:</strong> comprar o índice e esperar.</li>
      </ul>
      <p>Na carteira simulada aparece também a <strong>renda fixa (CDI)</strong>: não entra no critério estatístico, mas mostra se valeu a pena correr o risco da bolsa.</p>
    </>,
    noQuant: ({ est, b1, d }) => est && b1 && <>Até agora: regra {percentual(est.retorno_acumulado, 2, true)}, seguir toda notícia {percentual(b1.retorno_acumulado, 2, true)}{d?.carteiras?.cdi ? `, renda fixa ${percentual(d.carteiras.cdi.retorno_acumulado, 2, true)}` : ""}.</>,
  },
  {
    id: "sorte", modulo: "metodo", titulo: "Sorte, amostra e p-valor",
    frase: "Com poucas operações, lucro ou prejuízo ainda é quase só sorte.",
    corpo: <>
      <p>Cada operação tem um resultado que varia muito. A média de poucas operações é instável; o <strong>erro padrão</strong> diz quanto ela pode mudar e cai com a raiz do número de casos.</p>
      <p>O <strong>p-valor</strong> responde: "se a regra não tivesse vantagem nenhuma, qual a chance de ver um resultado tão bom só por acaso?". O projeto só declara o sinal demonstrado se o p-valor ficar abaixo de 5% contra o Ibovespa <em>e</em> contra "seguir toda notícia", e se o retorno também for maior que os dois. Caso contrário, a conclusão é "sinal não demonstrado" — que é um resultado válido.</p>
    </>,
    formula: "t = média ÷ (desvio ÷ √n)",
    noQuant: ({ d }) => {
      const m = d?.maturidade;
      const h = d?.historico_regra;
      if (!m) return null;
      return <>Até agora: {m.pregoes} pregões e {m.decisoes} decisões executadas (referência mínima: {m.meta.pregoes} e {m.meta.decisoes}).{h?.intervalo_aproximado_95 ? ` A média por decisão está entre ${percentual(h.intervalo_aproximado_95[0], 2, true)} e ${percentual(h.intervalo_aproximado_95[1], 2, true)}, com 95% de confiança aproximada.` : ""}</>;
    },
  },
  {
    id: "confianca", modulo: "metodo", titulo: "A confiança da IA não é probabilidade",
    frase: "\"80% de confiança\" não significa acertar 8 em cada 10 vezes.",
    corpo: <>
      <p>O número que o modelo declara é uma autoavaliação, não uma frequência medida. Um modelo pode dizer 90% e acertar metade das vezes.</p>
      <p><strong>Calibração</strong> compara a confiança declarada com o acerto observado, em faixas. O <strong>escore de Brier</strong> resume o erro: 0 é perfeito e 0,25 é o que se obtém dizendo sempre 50%. Até ser medido, o limiar funciona só como um corte de ordenação.</p>
    </>,
    formula: "Brier = média de (confiança − acertou)², com acertou = 1 ou 0",
  },
  {
    id: "limites", modulo: "metodo", titulo: "Custos, impostos e limites",
    frase: "Resultado histórico com dinheiro fictício não é promessa nem recomendação.",
    corpo: <>
      <p>Corretagem, emolumentos da B3 e a diferença entre o preço esperado e o executado (<em>slippage</em>) reduzem o retorno real de quem opera. Ganhos com ações também pagam imposto de renda, e isso não está modelado aqui.</p>
      <p>Somam-se histórico curto, poucos eventos, carteira escolhida hoje e o risco de o modelo de IA já conhecer o passado. Tudo isso limita as conclusões. Nada aqui é recomendação de investimento.</p>
    </>,
    noQuant: ({ d }) => d && <>Custo por operação configurado: {d.custo_por_operacao ? percentual(d.custo_por_operacao, 3) : "zero (ainda não há valores aprovados)"}. Impostos: não modelados.</>,
  },
];

const GLOSSARIO = [
  ["Ação", "Fração do capital de uma empresa negociada na bolsa."],
  ["B3", "A bolsa de valores brasileira."],
  ["Baseline", "Alternativa simples usada como comparação."],
  ["Benchmark", "Referência de desempenho, como o Ibovespa."],
  ["Caixa", "Parte do dinheiro que não está investida."],
  ["CDI", "Taxa de referência da renda fixa, próxima da Selic."],
  ["Drawdown", "Queda do patrimônio em relação ao pico anterior."],
  ["Exposição", "Fração do patrimônio aplicada em ações."],
  ["Fechamento", "Último preço de uma ação no pregão."],
  ["Look-ahead", "Usar, sem querer, informação que ainda não existia."],
  ["p-valor", "Chance de um resultado tão bom só por acaso, se não houvesse vantagem."],
  ["Pregão", "Dia de negociação na bolsa."],
  ["Proventos", "Dividendos e juros sobre capital próprio pagos aos acionistas."],
  ["Retorno real", "Retorno descontada a inflação."],
  ["Viés de sobrevivência", "Distorção por olhar só quem sobreviveu até hoje."],
  ["Volatilidade", "Medida de quanto os retornos variam."],
];

/* ------------------------------------------------------------- calculadoras */

function Campo({ rotulo, valor, aoMudar, ...resto }) {
  return (
    <label>{rotulo}
      <input type="number" inputMode="decimal" value={valor} onChange={(e) => aoMudar(e.target.value)} {...resto} />
    </label>
  );
}

function CalculadoraComposta() {
  const [valor, setValor] = useState(1000);
  const [aporte, setAporte] = useState(200);
  const [taxa, setTaxa] = useState(0.8);
  const [meses, setMeses] = useState(24);
  const principal = Math.max(0, numero(valor));
  const mensal = Math.max(0, numero(aporte));
  const juros = Math.max(-99, numero(taxa)) / 100;
  const prazo = limitar(Math.round(numero(meses)), 0, 600);
  let saldo = principal;
  for (let i = 0; i < prazo; i += 1) saldo = saldo * (1 + juros) + mensal;
  const aportado = principal + mensal * prazo;
  const rendimento = saldo - aportado;
  const parteAportada = saldo > 0 ? limitar(Math.min(aportado, saldo) / saldo, 0, 1) : 1;
  return (
    <Cartao titulo="Juros compostos" className="estudo-calculadora">
      <p>Valor inicial, aporte no fim de cada mês e uma taxa mensal hipotética. Não é previsão.</p>
      <div className="estudo-campos">
        <Campo rotulo="Valor inicial (R$)" valor={valor} aoMudar={setValor} min="0" />
        <Campo rotulo="Aporte mensal (R$)" valor={aporte} aoMudar={setAporte} min="0" />
        <Campo rotulo="Taxa ao mês (%)" valor={taxa} aoMudar={setTaxa} step="0.1" />
        <Campo rotulo="Prazo (meses)" valor={meses} aoMudar={setMeses} min="0" max="600" inputMode="numeric" />
      </div>
      <div className="estudo-resultado">
        <span>Saldo ao fim de {prazo} {prazo === 1 ? "mês" : "meses"}</span>
        <strong>{dinheiro(saldo)}</strong>
        <div className="estudo-barra" aria-hidden="true">
          <div style={{ width: `${parteAportada * 100}%` }} />
        </div>
        <div className="estudo-barra-legenda">
          <span><i className="aportado" />Você colocou {dinheiro(aportado)}</span>
          <span><i className="juros" />{rendimento >= 0 ? "Juros" : "Perda"}: {dinheiro(Math.abs(rendimento))}</span>
        </div>
      </div>
      <small className="sutil">{numero(taxa).toLocaleString("pt-BR")}% ao mês equivalem a {percentual((1 + juros) ** 12 - 1, 2)} ao ano. Sem impostos, tarifas ou inflação.</small>
    </Cartao>
  );
}

const QUEDAS_COMUNS = [0.1, 0.2, 0.3, 0.5, 0.8];

function CalculadoraQueda() {
  const [valor, setValor] = useState(10000);
  const [queda, setQueda] = useState(20);
  const inicial = Math.max(0, numero(valor));
  const fracao = limitar(numero(queda), 0, 99.9) / 100;
  const restante = inicial * (1 - fracao);
  const recuperacao = 1 / (1 - fracao) - 1;
  return (
    <Cartao titulo="Queda e recuperação" className="estudo-calculadora">
      <p>Depois de uma perda, o ganho incide sobre um saldo menor. Por isso a volta exige mais.</p>
      <div className="estudo-campos">
        <Campo rotulo="Valor antes da queda (R$)" valor={valor} aoMudar={setValor} min="0" />
        <Campo rotulo="Queda (%)" valor={queda} aoMudar={setQueda} min="0" max="99.9" step="1" />
      </div>
      <div className="estudo-metricas">
        <div><span>Depois da queda</span><strong>{dinheiro(restante)}</strong></div>
        <div><span>Alta para voltar</span><strong className="tom-texto-negativo">{percentual(recuperacao)}</strong></div>
      </div>
      <table className="estudo-tabela">
        <thead><tr><th>Se cair</th><th className="num">precisa subir</th></tr></thead>
        <tbody>
          {QUEDAS_COMUNS.map((q) => (
            <tr key={q}><td>{percentual(q, 0)}</td><td className="num">{percentual(1 / (1 - q) - 1)}</td></tr>
          ))}
        </tbody>
      </table>
    </Cartao>
  );
}

function CalculadoraReal() {
  const [nominal, setNominal] = useState(10);
  const [inflacao, setInflacao] = useState(4.5);
  const n = numero(nominal) / 100;
  const i = Math.max(-99, numero(inflacao)) / 100;
  const real = (1 + n) / (1 + i) - 1;
  return (
    <Cartao titulo="Retorno real" className="estudo-calculadora">
      <p>Quanto o poder de compra mudou depois de descontar a inflação do mesmo período.</p>
      <div className="estudo-campos">
        <Campo rotulo="Retorno no período (%)" valor={nominal} aoMudar={setNominal} step="0.1" />
        <Campo rotulo="Inflação no período (%)" valor={inflacao} aoMudar={setInflacao} step="0.1" />
      </div>
      <div className="estudo-metricas">
        <div><span>Retorno real</span><strong className={real >= 0 ? "tom-texto-positivo" : "tom-texto-negativo"}>{percentual(real, 2, true)}</strong></div>
        <div><span>Conta aproximada (subtrair)</span><strong>{percentual(n - i, 2, true)}</strong></div>
      </div>
      <small className="sutil">Os valores de exemplo são hipotéticos; use a inflação oficial (IPCA) do período que você quer analisar.</small>
    </Cartao>
  );
}

// Valor crítico da normal padrão para teste unilateral a 5%.
const Z_5_UNILATERAL = 1.645;

function CalculadoraAmostra({ decisoesAtuais }) {
  const [media, setMedia] = useState(0.5);
  const [desvio, setDesvio] = useState(4);
  const mu = numero(media) / 100;
  const sigma = Math.abs(numero(desvio)) / 100;
  const n = mu > 0 && sigma > 0 ? Math.ceil(((Z_5_UNILATERAL * sigma) / mu) ** 2) : null;
  return (
    <Cartao titulo="Quantas operações preciso?" className="estudo-calculadora">
      <p>Se cada operação ganhasse em média um certo valor, com uma certa variação, quantas seriam necessárias para o resultado deixar de parecer sorte (p &lt; 5%)?</p>
      <div className="estudo-campos">
        <Campo rotulo="Ganho médio por operação (%)" valor={media} aoMudar={setMedia} step="0.1" />
        <Campo rotulo="Variação típica por operação (%)" valor={desvio} aoMudar={setDesvio} min="0" step="0.5" />
      </div>
      <div className="estudo-resultado">
        <span>Operações necessárias, aproximadamente</span>
        <strong>{n == null ? "—" : n.toLocaleString("pt-BR")}</strong>
        <small>
          {n == null ? "Com ganho médio zero ou negativo não há vantagem a demonstrar."
            : `É o ponto em que um resultado médio exatamente igual a esse passaria no teste.${finito(decisoesAtuais) ? ` Até agora, o QUANT executou ${decisoesAtuais} ${Number(decisoesAtuais) === 1 ? "decisão" : "decisões"}.` : ""}`}
        </small>
      </div>
      <small className="sutil">Aproximação pela normal: n ≈ (1,645 × variação ÷ média)². Com metade do ganho médio, são necessárias quatro vezes mais operações.</small>
    </Cartao>
  );
}

/* --------------------------------------------------------------- estrutura */

const NUMERADAS = LICOES.map((l, i) => ({ ...l, numero: i + 1 }));

const ABAS = [
  ["licoes", "Lições", LICOES.length],
  ["calculadoras", "Calculadoras", 4],
  ["glossario", "Glossário", GLOSSARIO.length],
];
const CHAVE_ABA = "quant.estudos.aba";

function lerAba() {
  try {
    const salva = localStorage.getItem(CHAVE_ABA);
    return ABAS.some(([id]) => id === salva) ? salva : "licoes";
  } catch { return "licoes"; }
}

function Licao({ licao, aberta, aoAlternar, contexto }) {
  const noQuant = aberta ? licao.noQuant?.(contexto) : null;
  const corpoId = `estudo-corpo-${licao.id}`;
  return (
    <li className={`estudo-licao ${aberta ? "aberta" : ""}`}>
      <button type="button" className="estudo-licao-cabeca" aria-expanded={aberta} aria-controls={corpoId}
        onClick={() => aoAlternar(licao.id)}>
        <span className="estudo-licao-numero">{licao.numero}</span>
        <span className="estudo-licao-titulo">
          <strong>{licao.titulo}</strong>
          <small>{licao.frase}</small>
        </span>
        <svg className="estudo-licao-seta" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {aberta && (
        <div className="estudo-licao-corpo" id={corpoId}>
          {licao.corpo}
          {licao.formula && <div className="estudo-formula">{licao.formula}</div>}
          {noQuant && (
            <div className="estudo-no-quant">
              <Icone nome="grafico" tamanho={16} />
              <p><strong>No QUANT agora:</strong> {noQuant}</p>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function Fotografia({ d, erro, carregando }) {
  const est = d?.carteiras?.estrategia;
  const ibov = d?.carteiras?.ibovespa;
  const tom = (v) => (v > 0 ? "tom-texto-positivo" : v < 0 ? "tom-texto-negativo" : "");
  let conteudo;
  if (carregando && !d) conteudo = <p className="sutil">Carregando os números da simulação…</p>;
  else if (erro) conteudo = <p className="sutil">Não foi possível carregar a simulação agora. As lições continuam válidas.</p>;
  else if (!est || !ibov) {
    conteudo = <p className="sutil">{d?.mensagem || "Ainda não há histórico de preços suficiente."} Quando houver pregões, as lições passam a mostrar os números reais da simulação.</p>;
  } else {
    conteudo = (
      <dl className="estudos-foto-numeros">
        <div><dt>Estratégia</dt><dd className={tom(est.retorno_acumulado)}>{percentual(est.retorno_acumulado, 2, true)}</dd></div>
        <div><dt>Ibovespa</dt><dd className={tom(ibov.retorno_acumulado)}>{percentual(ibov.retorno_acumulado, 2, true)}</dd></div>
        <div><dt>Investido, em média</dt><dd>{percentual(est.exposicao_media)}</dd></div>
        <div><dt>Maior queda</dt><dd>{percentual(est.drawdown_maximo, 2)}</dd></div>
      </dl>
    );
  }
  return (
    <section className="estudos-foto">
      <header>
        <strong>Os números de hoje</strong>
        <small>{d?.ultimo_fechamento
          ? `fechamento de ${new Date(`${d.ultimo_fechamento}T12:00:00-03:00`).toLocaleDateString("pt-BR")}`
          : "dinheiro fictício"}</small>
      </header>
      {conteudo}
      {d?.maturidade && <p className="estudos-foto-nota"><Icone nome="escudo" tamanho={14} /> {d.maturidade.texto}</p>}
    </section>
  );
}

function Licoes({ contexto, fotografia }) {
  const [abertas, setAbertas] = useState(() => new Set([LICOES[0].id]));
  const alternar = (id) => setAbertas((atual) => {
    const novo = new Set(atual);
    if (novo.has(id)) novo.delete(id); else novo.add(id);
    return novo;
  });
  const todas = abertas.size === LICOES.length;
  return (
    <div className="estudos-corpo">
      <aside className="estudos-lateral">{fotografia}</aside>
      <div className="estudos-modulos">
        <div className="estudos-controle">
          <span className="sutil">Toque em uma lição para abrir.</span>
          <button type="button" className="botao-link"
            onClick={() => setAbertas(new Set(todas ? [] : LICOES.map((l) => l.id)))}>
            {todas ? "Recolher todas" : "Abrir todas"}
          </button>
        </div>
        {MODULOS.map((m, i) => (
          <section key={m.id} className="estudos-modulo">
            <header className="estudos-modulo-topo">
              <small>Parte {i + 1}</small>
              <h2>{m.titulo}</h2>
              <p>{m.texto}</p>
            </header>
            <ol className="estudos-lista">
              {NUMERADAS.filter((l) => l.modulo === m.id).map((l) => (
                <Licao key={l.id} licao={l} aberta={abertas.has(l.id)} aoAlternar={alternar} contexto={contexto} />
              ))}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}

export default function Estudos({ base }) {
  const { dados: d, erro, carregando } = useApi(`/api/simulacao?base=${base}`);
  const [aba, setAba] = useState(lerAba);

  function escolher(id) {
    setAba(id);
    try { localStorage.setItem(CHAVE_ABA, id); } catch { /* sem armazenamento: ignora */ }
  }

  const est = d?.carteiras?.estrategia;
  const contexto = {
    d, est, ibov: d?.carteiras?.ibovespa, b1: d?.carteiras?.baseline_1,
    capital: d?.capital_inicial ?? 100000,
    caixaPct: d?.alocacao && est?.patrimonio ? d.alocacao.caixa / est.patrimonio : null,
  };

  return (
    <div className="estudos">
      <section className="estudos-abertura">
        <span className="estudos-etiqueta">Guia do zero · sem pré-requisitos</span>
        <h2>Entenda a economia por trás dos números</h2>
        <p>Do conceito de retorno até como o QUANT decide se uma ideia funcionou, em lições curtas e com os números atuais da simulação.</p>
      </section>

      <div className="estudos-abas" role="tablist" aria-label="Seções do guia">
        {ABAS.map(([id, nome, quantos]) => (
          <button key={id} type="button" role="tab" aria-selected={aba === id}
            className={aba === id ? "ativo" : ""} onClick={() => escolher(id)}>
            {nome}<span>{quantos}</span>
          </button>
        ))}
      </div>

      {aba === "licoes" && (
        <Licoes contexto={contexto} fotografia={<Fotografia d={d} erro={erro} carregando={carregando} />} />
      )}

      {aba === "calculadoras" && (
        <section className="estudos-modulo">
          <header className="estudos-modulo-topo">
            <h2>Calculadoras</h2>
            <p>Mude os valores e veja os conceitos das lições funcionando. Todas usam hipóteses suas; nenhuma é previsão.</p>
          </header>
          <div className="estudos-calculadoras">
            <CalculadoraComposta />
            <CalculadoraQueda />
            <CalculadoraReal />
            <CalculadoraAmostra decisoesAtuais={d?.maturidade?.decisoes} />
          </div>
        </section>
      )}

      {aba === "glossario" && (
        <section className="estudos-modulo">
          <header className="estudos-modulo-topo">
            <h2>Glossário</h2>
            <p>Os termos que aparecem no QUANT, em uma linha cada.</p>
          </header>
          <dl className="estudos-glossario">
            {GLOSSARIO.map(([termo, definicao]) => (
              <div key={termo}><dt>{termo}</dt><dd>{definicao}</dd></div>
            ))}
          </dl>
        </section>
      )}

    </div>
  );
}
