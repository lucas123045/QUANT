import { useState } from "react";
import { useApi, formatarData, formatarNumero, formatarPreco } from "../api.js";
import { Cartao, Estado, EtiquetaDecisao, EtiquetaSentimento } from "../ui.jsx";
import GraficoPatrimonio, { SERIES, reais } from "../GraficoPatrimonio.jsx";
import { BarrasComparacao, BarrasRendimento, COR_TICKER, Minigrafico, Rosca } from "../graficos.jsx";

const dia = (iso) => formatarData(iso + "T12:00:00-03:00", false);
const pct = (v, sinal = true) =>
  v === null || v === undefined ? "—" : `${sinal && v >= 0 ? "+" : ""}${formatarNumero(v * 100, 2)}%`;
const tom = (v) => (!v ? "" : v > 0 ? "tom-texto-positivo" : "tom-texto-negativo");

const SITUACOES = {
  na_carteira: { texto: "Na carteira", classe: "tom-positivo" },
  compra_agendada: { texto: "Compra agendada", classe: "tom-alerta" },
  venda_agendada: { texto: "Venda agendada", classe: "tom-negativo" },
  sem_posicao: { texto: "Sem posição", classe: "" },
};

const PERIODOS = [["7D", 5], ["30D", 21], ["Tudo", Infinity]];

function Dinheiro({ valor, oculto, casas = 2, className = "" }) {
  return <span className={className}>{oculto ? "R$ ••••••" : reais(valor, casas)}</span>;
}

/* ------------------------------------------------------------------ saldo */
function Saldo({ d, oculto, setOculto }) {
  const est = d.carteiras.estrategia;
  const ganho = est.patrimonio - d.capital_inicial;
  const investido = d.alocacao.acoes.reduce((s, a) => s + a.valor, 0);
  const rendimentoPosicoes = d.posicoes_abertas.reduce((s, p) => s + p.resultado, 0);
  return (
    <section className="fin-saldo">
      <div className="fin-saldo-topo">
        <span className="rotulo">Saldo total</span>
        <button className="fin-olho" onClick={() => setOculto(!oculto)} aria-label={oculto ? "Mostrar valores" : "Esconder valores"}>
          {oculto ? "mostrar" : "esconder"}
        </button>
      </div>
      <Dinheiro valor={est.patrimonio} oculto={oculto} className="fin-saldo-valor" />
      <div className={`fin-saldo-delta ${tom(ganho)}`}>
        {oculto ? "••••" : `${ganho >= 0 ? "+" : "−"}${reais(Math.abs(ganho), 2)}`} ({pct(est.retorno_acumulado)}) desde {dia(d.inicio)}
      </div>
      <div className="fin-saldo-partes">
        <div><span className="rotulo">Investido</span><Dinheiro valor={investido} oculto={oculto} /></div>
        <div><span className="rotulo">Em caixa</span><Dinheiro valor={d.alocacao.caixa} oculto={oculto} /></div>
        <div>
          <span className="rotulo">Rendimento das posições</span>
          <span className={tom(rendimentoPosicoes)}>
            {oculto ? "R$ ••••" : `${rendimentoPosicoes >= 0 ? "+" : "−"}${reais(Math.abs(rendimentoPosicoes), 2)}`}
          </span>
        </div>
      </div>
      <p className="nota">Dinheiro fictício · preços reais de fechamento até {dia(d.ultimo_fechamento)}.</p>
    </section>
  );
}

function Alocacao({ d, oculto }) {
  const fatias = [
    ...d.alocacao.acoes.map((a) => ({ chave: a.ticker, rotulo: a.ticker, valor: a.valor })),
    { chave: "CAIXA", rotulo: "Caixa", valor: d.alocacao.caixa },
  ];
  const total = fatias.reduce((s, f) => s + f.valor, 0);
  return (
    <Cartao titulo="Onde está o dinheiro">
      <div className="fin-alocacao">
        <Rosca fatias={fatias} formatar={(v) => (oculto ? "R$ ••••" : reais(v))}
          centro={<><span className="rotulo">Investido</span><strong>{pct(1 - d.alocacao.caixa / total, false)}</strong></>} />
        <ul className="fin-legenda">
          {fatias.map((f) => (
            <li key={f.chave}>
              <span className="grafico-amostra quadrada" style={{ background: COR_TICKER[f.chave] }} />
              <span>{f.rotulo}</span>
              <span className="sutil">{pct(f.valor / total, false)}</span>
              <Dinheiro valor={f.valor} oculto={oculto} casas={0} className="num" />
            </li>
          ))}
        </ul>
      </div>
      <p className="nota">Cada compra usa até {Math.round(d.parametros.max_posicao_pct * 100)}% do saldo; o resto fica em caixa.</p>
    </Cartao>
  );
}

/* ------------------------------------------------------------- comparação */
function Comparacao({ d }) {
  const itens = SERIES.map((s) => ({ chave: s.chave, rotulo: s.nome.split(" (")[0], valor: d.carteiras[s.chave].retorno_acumulado, cor: s.cor }));
  const est = d.carteiras.estrategia;
  const ibov = d.carteiras.ibovespa;
  const ganhou = est.retorno_acumulado > ibov.retorno_acumulado;
  return (
    <Cartao titulo="Rendimento comparado">
      <BarrasComparacao itens={itens} formatar={(v) => pct(v)} />
      <p className="fin-explica">
        Desde {dia(d.inicio)}, a carteira da regra {est.retorno_acumulado >= 0 ? "rendeu" : "perdeu"}{" "}
        <strong>{pct(Math.abs(est.retorno_acumulado), false)}</strong> e o Ibovespa{" "}
        {ibov.retorno_acumulado >= 0 ? "subiu" : "caiu"} <strong>{pct(Math.abs(ibov.retorno_acumulado), false)}</strong>
        {ganhou ? ": a regra está na frente." : ": por enquanto, o Ibovespa está na frente."}
      </p>
      <p className="nota">
        A regra fica em média {pct(est.exposicao_media, false)} investida; o Ibovespa, 100%. Em mercado de alta, ficar em caixa
        pesa contra a regra mesmo quando ela acerta a ação. Com poucos dias, a diferença ainda é quase só ruído.
      </p>
    </Cartao>
  );
}

function Evolucao({ d }) {
  const [periodo, setPeriodo] = useState("Tudo");
  const quantos = PERIODOS.find(([n]) => n === periodo)[1];
  const serie = d.serie.slice(-Math.min(d.serie.length, quantos === Infinity ? d.serie.length : quantos + 1));
  return (
    <Cartao titulo="Evolução do patrimônio"
      acao={
        <div className="fin-chips">
          {PERIODOS.map(([nome]) => (
            <button key={nome} className={periodo === nome ? "ativo" : ""} onClick={() => setPeriodo(nome)}>{nome}</button>
          ))}
        </div>
      }>
      <GraficoPatrimonio serie={serie} capital={d.capital_inicial} />
    </Cartao>
  );
}

/* ----------------------------------------------------------------- ativos */
function CartaoAtivo({ a, oculto, saldo, fracao }) {
  const s = SITUACOES[a.situacao];
  const u = a.ultima_decisao;
  return (
    <article className="fin-ativo" style={{ "--cor-ativo": COR_TICKER[a.ticker] }}>
      <header>
        <div>
          <strong className="ticker">{a.ticker}</strong>
          <span className="sutil">{a.empresa}</span>
        </div>
        <span className={`etiqueta ${s.classe}`}>{s.texto}</span>
      </header>
      <div className="fin-ativo-preco">
        <div>
          <span className="fin-ativo-valor">{a.preco ? `R$ ${formatarPreco(a.preco)}` : "—"}</span>
          <span className={tom(a.variacao_dia)}>{pct(a.variacao_dia)} no dia</span>
        </div>
        <div className="fin-ativo-mini">
          <Minigrafico pontos={a.minigrafico} />
          <span className={tom(a.variacao_30d)}>{pct(a.variacao_30d)} em 30 dias</span>
        </div>
      </div>

      {a.posicao && (
        <div className="fin-ativo-posicao">
          <span>Você tem <Dinheiro valor={a.posicao.valor} oculto={oculto} /></span>
          <span className={tom(a.posicao.retorno)}>
            {pct(a.posicao.retorno)} desde {dia(a.posicao.entrada)} (comprou a R$ {formatarPreco(a.posicao.preco_entrada)})
          </span>
        </div>
      )}
      {a.situacao === "compra_agendada" && (
        <div className="fin-ativo-agenda">
          Compra no fechamento do próximo pregão, com até {Math.round(fracao * 100)}% do saldo
          (≈ <Dinheiro valor={saldo * fracao} oculto={oculto} casas={0} />). O rendimento só existe depois da compra.
        </div>
      )}
      {a.situacao === "venda_agendada" && (
        <div className="fin-ativo-agenda">
          {a.posicao ? "Venda de toda a posição no fechamento do próximo pregão."
            : "A regra mandou vender, mas não há posição: nada acontece."}
        </div>
      )}

      <div className="fin-ativo-analise">
        <span className="rotulo">Última notícia analisada</span>
        {u ? (
          <>
            <p>{u.resumo}</p>
            {u.trecho_fonte && <blockquote>“{u.trecho_fonte}”</blockquote>}
            <div className="fin-ativo-chips">
              <span className="sutil">A IA classificou:</span>
              <EtiquetaSentimento classificacao={u.sentimento ? { sentimento: u.sentimento, probabilidade: u.probabilidade } : null} />
              <span className="etiqueta">{u.confirmado ? "confirmado" : "não confirmado"}</span>
            </div>
            <div className="fin-ativo-chips">
              <span className="sutil">A regra decidiu:</span><EtiquetaDecisao decisao={u.decisao} />
            </div>
            <small className="sutil">{u.motivo}. {u.fonte} · {formatarData(u.publicado)}
              {u.url && <> · <a href={u.url} target="_blank" rel="noreferrer">ler notícia</a></>}</small>
          </>
        ) : <p className="sutil">Nenhuma notícia sobre {a.empresa} passou pela IA ainda.</p>}
      </div>
    </article>
  );
}

/* ------------------------------------------------- rendimento e histórico */
function Rendimentos({ d, oculto }) {
  const operacoes = [...d.operacoes_encerradas, ...d.posicoes_abertas].sort((a, b) => a.entrada.localeCompare(b.entrada));
  const h = d.historico_regra;
  const [valor, setValor] = useState(1000);
  return (
    <div className="grade">
      <Cartao titulo="Rendimento de cada decisão" className="span-2">
        <Estado vazio={!operacoes.length} mensagemVazio="Nenhuma compra executada ainda.">
          <BarrasRendimento formatar={(v) => pct(v)}
            itens={operacoes.map((o) => ({
              valor: o.retorno, rotulo: o.ticker,
              detalhe: `${o.ticker}: comprou a R$ ${formatarPreco(o.preco_entrada)} em ${dia(o.entrada)}; ` +
                `${o.aberta ? "hoje" : `vendeu em ${dia(o.saida)}`} a R$ ${formatarPreco(o.preco_saida)}.`,
            }))} />
          <div className="calculadora-entrada">
            <label htmlFor="valor-simulado">E se eu tivesse aplicado</label>
            <div className="campo-moeda">
              <span>R$</span>
              <input id="valor-simulado" type="number" min="0" step="100" value={valor}
                onChange={(e) => setValor(Math.max(0, Number(e.target.value) || 0))} />
            </div>
            <span className="sutil">em cada decisão:</span>
          </div>
          <ul className="fin-ese">
            {operacoes.map((o, i) => (
              <li key={i}>
                <span className="ticker">{o.ticker}</span>
                <span className="sutil">{dia(o.entrada)} → {o.aberta ? "hoje" : dia(o.saida)}</span>
                <span className="num">{reais(valor, 2)}</span>
                <span className="seta">→</span>
                <strong className={`num ${tom(o.retorno)}`}>{reais(valor * (1 + o.retorno), 2)}</strong>
              </li>
            ))}
          </ul>
        </Estado>
      </Cartao>

      <Cartao titulo="Histórico da regra">
        <dl className="fin-numeros">
          <div><dt>Decisões executadas</dt><dd>{h.n}</dd></div>
          <div><dt>Rendimento médio</dt><dd className={tom(h.media)}>{pct(h.media)}</dd></div>
          <div><dt>Acertos (rendeu &gt; 0)</dt><dd>{h.taxa_acerto == null ? "—" : `${Math.round(h.taxa_acerto * 100)}%`}</dd></div>
          <div><dt>Melhor / pior</dt><dd>{pct(h.melhor)} / {pct(h.pior)}</dd></div>
          <div className="largo">
            <dt>Margem de incerteza da média</dt>
            <dd>{h.intervalo_aproximado_95 ? `${pct(h.intervalo_aproximado_95[0])} a ${pct(h.intervalo_aproximado_95[1])}` : "precisa de 2+ decisões"}</dd>
          </div>
        </dl>
        <p className="nota">
          Isso é o que aconteceu, não uma previsão. Se a margem de incerteza cruza o zero, ainda não dá para dizer
          que a regra ganha dinheiro.
        </p>
      </Cartao>
    </div>
  );
}

/* --------------------------------------------------- agenda e extrato */
function AgendaExtrato({ d, oculto }) {
  return (
    <div className="grade">
      <Cartao titulo={`Próximas movimentações · ${d.pendentes.length}`}>
        <Estado vazio={!d.pendentes.length} mensagemVazio="Nada agendado.">
          <ul className="fin-extrato">
            {d.pendentes.map((p, i) => (
              <li key={i}>
                <EtiquetaDecisao decisao={p.decisao} />
                <div><strong className="ticker">{p.ticker}</strong><small className="sutil">notícia de {formatarData(p.publicado)}</small></div>
                <span className="sutil">próximo fechamento</span>
              </li>
            ))}
          </ul>
        </Estado>
      </Cartao>
      <Cartao titulo="Extrato" className="span-2">
        <Estado vazio={!d.extrato.length} mensagemVazio="Nenhuma movimentação ainda.">
          <ul className="fin-extrato">
            {d.extrato.map((l, i) => (
              <li key={i}>
                <span className="sutil num">{dia(l.data)}</span>
                <div>
                  <strong>{l.tipo === "compra" ? "Compra" : "Venda"} de <span className="ticker">{l.ticker}</span></strong>
                  <small className="sutil">{formatarNumero(l.quantidade ?? l.valor / l.preco, 2)} ações a R$ {formatarPreco(l.preco)}</small>
                </div>
                <span className={`num ${l.tipo === "compra" ? "" : tom(l.resultado)}`}>
                  {oculto ? "R$ ••••" : `${l.tipo === "compra" ? "−" : "+"}${reais(l.valor, 2)}`}
                </span>
              </li>
            ))}
          </ul>
        </Estado>
        {!!d.ordens_ignoradas?.length && (
          <p className="nota">
            Ordens não executadas: {d.ordens_ignoradas.map((o) => `${o.ticker} (${o.decisao}, ${o.razao})`).join("; ")}.
          </p>
        )}
      </Cartao>
    </div>
  );
}

/* ---------------------------------------------------------- como funciona */
function ComoFunciona({ d }) {
  const p = d.parametros;
  return (
    <Cartao titulo="Como funciona">
      <ol className="fin-passos">
        <li><strong>A IA lê a notícia.</strong> Diz qual empresa, que tipo de evento, se é bom ou ruim e com que confiança, e mostra a frase do texto que comprova.</li>
        <li><strong>A regra decide, não a IA.</strong> Compra se o evento for confirmado, positivo, com confiança acima de {formatarNumero(p.limiar_probabilidade, 2)} e sem notícia negativa da mesma empresa nos {p.janela_evento_recente_dias} dias anteriores. Vende no caso oposto. Senão, não faz nada.</li>
        <li><strong>A carteira executa no próximo pregão.</strong> Ao preço de fechamento real, com até {Math.round(p.max_posicao_pct * 100)}% do saldo por ação. Assim nunca se usa informação que não existia no momento.</li>
        <li><strong>Você acompanha.</strong> Saldo, posições, extrato e a comparação com quem só seguisse toda notícia positiva e com o Ibovespa.</li>
      </ol>
      <details className="fin-detalhe">
        <summary>Por que não aparece "quanto vai render"?</summary>
        <p>
          Ninguém sabe quanto uma ação vai render, e o sistema não finge saber. Mostrar uma previsão seria inventar um
          número. O que aparece aqui é o que já aconteceu: o rendimento de cada decisão e o histórico da regra, com a
          margem de incerteza. É justamente isso que o trabalho quer medir: se as decisões tomadas a partir das notícias
          rendem mais que as alternativas simples.
        </p>
      </details>
      <details className="fin-detalhe">
        <summary>O que este resultado prova?</summary>
        <p>
          {d.congelada ? "A regra está congelada: este acompanhamento é uma validação prospectiva." :
            "Ainda nada: a regra não foi congelada, então o resultado é exploratório."}{" "}
          Com poucos dias e poucas decisões, ganhar ou perder do Ibovespa é quase só sorte. A conclusão do trabalho vem
          do período de teste, com o critério estatístico definido antes.
        </p>
      </details>
    </Cartao>
  );
}

/* ------------------------------------------------------------------ página */
export default function Simulacao({ base }) {
  const { dados: d, erro, carregando, recarregar } = useApi(`/api/simulacao?base=${base}`);
  const [oculto, setOculto] = useState(false);

  return (
    <Estado carregando={carregando && !d} erro={erro}>
      {d && (
        <div className="pilha fin">
          <div className={`aviso ${d.congelada ? "" : "tom-alerta"}`}>
            {d.aviso} <button className="botao-link" onClick={recarregar}>Atualizar</button>
          </div>

          {d.estado === "ok" ? (
            <>
              <div className="grade">
                <div className="span-2 fin-celula"><Saldo d={d} oculto={oculto} setOculto={setOculto} /></div>
                <Alocacao d={d} oculto={oculto} />
              </div>
              <div className="grade">
                <div className="span-2 fin-celula"><Evolucao d={d} /></div>
                <Comparacao d={d} />
              </div>
            </>
          ) : (
            <section className="fin-saldo">
              <span className="rotulo">Saldo total</span>
              <span className="fin-saldo-valor">{reais(d.capital_inicial, 2)}</span>
              <p className="fin-explica">{d.mensagem} A carteira começa com {reais(d.capital_inicial)} fictícios, 100% em caixa.</p>
            </section>
          )}

          <section>
            <h2 className="fin-secao">Seus ativos</h2>
            <div className="fin-ativos">
              {(d.ativos || []).map((a) => (
                <CartaoAtivo key={a.ticker} a={a} oculto={oculto}
                  saldo={d.carteiras?.estrategia.patrimonio ?? d.capital_inicial} fracao={d.parametros.max_posicao_pct} />
              ))}
            </div>
          </section>

          {d.estado === "ok" && <Rendimentos d={d} oculto={oculto} />}
          {d.estado === "ok" ? <AgendaExtrato d={d} oculto={oculto} /> : null}
          <ComoFunciona d={d} />
        </div>
      )}
    </Estado>
  );
}
