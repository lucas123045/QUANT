import { useState } from "react";
import { VITRINE, useApi, formatarData, formatarNumero, formatarPreco, plural } from "../api.js";
import { Estado, EtiquetaDecisao, EtiquetaSentimento } from "../ui.jsx";
import GraficoPatrimonio, { SERIES, reais } from "../GraficoPatrimonio.jsx";
import { BarrasRendimento, COR_TICKER, Minigrafico, Rosca } from "../graficos.jsx";
import Icone from "../icones.jsx";

const dia = (iso) => formatarData(iso + "T12:00:00-03:00", false);
const pct = (v, sinal = true) => {
  if (v === null || v === undefined) return "—";
  if (Math.abs(v) < 0.00005) return "0%";  // zero (ou quase) não leva sinal
  return `${sinal && v > 0 ? "+" : ""}${formatarNumero(v * 100, 2)}%`;
};
const tom = (v) => (!v ? "" : v > 0 ? "tom-texto-positivo" : "tom-texto-negativo");

const PRODUTOS = {
  estrategia: { nome: "Estratégia QUANT", descricao: "Compra quando a IA encontra uma notícia boa e confirmada, seguindo a regra." },
  baseline_1: { nome: "Seguir toda notícia", descricao: "Compra em toda notícia positiva, sem filtro nenhum. Serve de comparação." },
  ibovespa: { nome: "Ibovespa", descricao: "O mercado inteiro, comprado no primeiro dia e guardado." },
  cdi: { nome: "Renda fixa (CDI)", descricao: "Tudo aplicado a 100% do CDI, sem bolsa. A alternativa que qualquer estratégia precisa superar." },
};

const SITUACOES = {
  na_carteira: { texto: "Na carteira", classe: "tom-positivo" },
  compra_agendada: { texto: "Compra agendada", classe: "tom-alerta" },
  venda_agendada: { texto: "Venda agendada", classe: "tom-negativo" },
  sem_posicao: { texto: "Sem posição", classe: "" },
};

const NIVEIS = {
  muito_cedo: { titulo: "Muito cedo para concluir", classe: "tom-negativo" },
  inicial: { titulo: "Histórico ainda curto", classe: "tom-alerta" },
  razoavel: { titulo: "Histórico razoável", classe: "tom-positivo" },
};

const PERIODOS = [["Semana", 5], ["Mês", 21], ["Tudo", Infinity]];

function Dinheiro({ valor, oculto, casas = 2, className = "" }) {
  return <span className={className}>{oculto ? "R$ ••••••" : reais(valor, casas)}</span>;
}

function Cartao({ titulo, subtitulo, acao, children, className = "" }) {
  return (
    <section className={`f-cartao ${className}`}>
      {(titulo || acao) && (
        <header className="f-cartao-topo">
          <div>
            {titulo && <h2>{titulo}</h2>}
            {subtitulo && <p>{subtitulo}</p>}
          </div>
          {acao}
        </header>
      )}
      {children}
    </section>
  );
}

/* ---------------------------------------------------------------- topo */
function Resumo({ d, oculto, setOculto }) {
  const est = d.carteiras?.estrategia;
  const saldo = est?.patrimonio ?? d.capital_inicial;
  const ganho = saldo - d.capital_inicial;
  const investido = d.alocacao ? d.alocacao.acoes.reduce((s, a) => s + a.valor, 0) : 0;
  const caixa = d.alocacao ? d.alocacao.caixa : d.capital_inicial;
  const rendimento = (d.posicoes_abertas || []).reduce((s, p) => s + p.resultado, 0);
  return (
    <div className="f-resumo">
      <section className="f-saldo">
        <div className="f-saldo-topo">
          <span>Seu saldo total</span>
          <button className="f-icone-botao" onClick={() => setOculto(!oculto)} aria-label={oculto ? "Mostrar valores" : "Esconder valores"}>
            <Icone nome={oculto ? "olho" : "olhoFechado"} tamanho={17} />
          </button>
        </div>
        <Dinheiro valor={saldo} oculto={oculto} className="f-saldo-valor" />
        <div className="f-saldo-rodape">
          <span className={`f-pilula ${ganho > 0 ? "positiva" : ganho < 0 ? "negativa" : ""}`}>
            {oculto ? "••••" : `${ganho >= 0 ? "+" : "−"}${reais(Math.abs(ganho), 2)}`} · {pct(est?.retorno_acumulado ?? 0)}
          </span>
          <span>{d.inicio ? `desde ${dia(d.inicio)}` : "começando agora"}</span>
        </div>
        <small>Dinheiro fictício · preços reais{d.ultimo_fechamento ? ` até ${dia(d.ultimo_fechamento)}` : ""}</small>
        <div className="f-saldo-partes so-celular">
          <div><small>Investido</small><Dinheiro valor={investido} oculto={oculto} casas={0} /></div>
          <div><small>Em caixa</small><Dinheiro valor={caixa} oculto={oculto} casas={0} /></div>
          <div>
            <small>Rendimento</small>
            <span className={tom(rendimento)}>{oculto ? "R$ ••••" : `${rendimento >= 0 ? "+" : "−"}${reais(Math.abs(rendimento), 0)}`}</span>
          </div>
        </div>
      </section>
      <Estatistica icone="grafico" rotulo="Investido em ações" valor={<Dinheiro valor={investido} oculto={oculto} />}
        detalhe={`${pct(saldo ? investido / saldo : 0, false)} do saldo`} />
      <Estatistica icone="dinheiro" rotulo="Em caixa" valor={<Dinheiro valor={caixa} oculto={oculto} />}
        detalhe="disponível para as próximas compras" />
      <Estatistica icone="alta" rotulo="Rendimento das posições"
        valor={<span className={tom(rendimento)}>{oculto ? "R$ ••••" : `${rendimento >= 0 ? "+" : "−"}${reais(Math.abs(rendimento), 2)}`}</span>}
        detalhe={plural(d.posicoes_abertas?.length || 0, "posição aberta", "posições abertas")} />
    </div>
  );
}

function Atalhos({ irPara }) {
  // Notícias, Análises e Decisões já estão na barra inferior.
  const itens = [
    ["estudos", "estudos", "Estudos"],
    ["painel", "painel", "Sistema"],
    ["acoes", "acoes", "Rodar"],
    ["configuracao", "configuracao", "Regras"],
  ];
  return (
    <nav className="f-atalhos so-celular" aria-label="Atalhos">
      {itens.map(([id, icone, nome]) => (
        <button key={id} onClick={() => irPara(id)}>
          <span><Icone nome={icone} tamanho={20} /></span>{nome}
        </button>
      ))}
    </nav>
  );
}

function Estatistica({ icone, rotulo, valor, detalhe }) {
  return (
    <section className="f-estat">
      <span className="f-estat-icone"><Icone nome={icone} tamanho={18} /></span>
      <span className="f-estat-valor">{valor}</span>
      <span className="f-estat-rotulo">{rotulo}</span>
      <small>{detalhe}</small>
    </section>
  );
}

function Maturidade({ m }) {
  const n = NIVEIS[m.nivel];
  const barra = (atual, meta) => `${Math.min(100, (atual / meta) * 100)}%`;
  return (
    <section className="f-maturidade">
      <span className={`f-estat-icone ${n.classe}`}><Icone nome="escudo" tamanho={18} /></span>
      <div className="f-maturidade-texto">
        <strong>{n.titulo}</strong>
        <p>{m.texto}</p>
      </div>
      <div className="f-maturidade-barras">
        <div>
          <span>Dias de pregão <b>{m.pregoes} / {m.meta.pregoes}</b></span>
          <div className="f-progresso"><div style={{ width: barra(m.pregoes, m.meta.pregoes) }} /></div>
        </div>
        <div>
          <span>Decisões <b>{m.decisoes} / {m.meta.decisoes}</b></span>
          <div className="f-progresso"><div style={{ width: barra(m.decisoes, m.meta.decisoes) }} /></div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------- gráfico + alocação */
function Evolucao({ d }) {
  const [periodo, setPeriodo] = useState("Tudo");
  const quantos = PERIODOS.find(([n]) => n === periodo)[1];
  const serie = quantos === Infinity ? d.serie : d.serie.slice(-(quantos + 1));
  return (
    <Cartao titulo="Evolução do patrimônio" subtitulo="Todos os produtos começaram com o mesmo valor"
      className="f-span-2"
      acao={
        <div className="f-segmentado">
          {PERIODOS.map(([nome]) => (
            <button key={nome} className={periodo === nome ? "ativo" : ""} onClick={() => setPeriodo(nome)}>{nome}</button>
          ))}
        </div>
      }>
      <GraficoPatrimonio serie={serie} capital={d.capital_inicial} />
    </Cartao>
  );
}

function Alocacao({ d, oculto }) {
  const fatias = [
    ...d.alocacao.acoes.map((a) => ({ chave: a.ticker, rotulo: a.ticker, valor: a.valor })),
    { chave: "CAIXA", rotulo: "Caixa", valor: d.alocacao.caixa },
  ];
  const total = fatias.reduce((s, f) => s + f.valor, 0);
  return (
    <Cartao titulo="Onde está o dinheiro" subtitulo={`Cada compra usa até ${Math.round(d.parametros.max_posicao_pct * 100)}% do saldo`}>
      <div className="f-alocacao">
        <Rosca fatias={fatias} formatar={(v) => (oculto ? "R$ ••••" : reais(v))}
          centro={<><small>Investido</small><strong>{pct(1 - d.alocacao.caixa / total, false)}</strong></>} />
        <ul className="f-legenda">
          {fatias.map((f) => (
            <li key={f.chave}>
              <span className="f-ponto" style={{ background: COR_TICKER[f.chave] }} />
              <span>{f.rotulo}</span>
              <span className="sutil">{pct(f.valor / total, false)}</span>
              <Dinheiro valor={f.valor} oculto={oculto} casas={0} className="f-legenda-valor" />
            </li>
          ))}
        </ul>
      </div>
    </Cartao>
  );
}

/* ----------------------------------------------------------- produtos */
function Produtos({ d, oculto }) {
  const melhor = Object.entries(d.carteiras).sort((a, b) => b[1].retorno_acumulado - a[1].retorno_acumulado)[0][0];
  const presentes = SERIES.filter((s) => d.carteiras[s.chave]);
  const est = d.carteiras.estrategia;
  const rendaFixa = d.carteiras.cdi;
  return (
    <section>
      <div className="f-secao">
        <h2>Produtos que você está testando</h2>
        <p>Mesmo valor inicial em todos. Compare quanto rendeu, quanto oscilou e quanto chegou a cair.</p>
      </div>
      <div className={`f-produtos ${presentes.length === 4 ? "quatro" : ""}`}>
        {presentes.map((s) => {
          const c = d.carteiras[s.chave];
          const p = PRODUTOS[s.chave];
          return (
            <article key={s.chave} className={`f-produto ${s.chave === "estrategia" ? "principal" : ""}`}>
              <header>
                <span className="f-ponto grande" style={{ background: s.cor }} />
                <div>
                  <strong>{p.nome}</strong>
                  <small>{p.descricao}</small>
                </div>
                {melhor === s.chave && <span className="f-selo">Maior rendimento</span>}
              </header>
              <div className="f-produto-meio">
                <div>
                  <span className={`f-produto-retorno ${tom(c.retorno_acumulado)}`}>{pct(c.retorno_acumulado)}</span>
                  <Dinheiro valor={c.patrimonio} oculto={oculto} className="sutil" />
                </div>
                <Minigrafico pontos={d.serie.map((x) => ({ data: x.data, preco: x[s.chave] })).filter((x) => x.preco != null)}
                  largura={120} altura={44} />
              </div>
              <dl className="f-produto-numeros">
                <div>
                  <dt>Oscilação</dt>
                  <dd><span className={`f-nivel ${c.oscilacao || ""}`}>{c.oscilacao || "—"}</span></dd>
                  <small className="sutil">
                    {s.chave === "cdi" ? "sem ações" : `${Math.round((c.exposicao_media ?? 1) * 100)}% em ações`}
                  </small>
                </div>
                <div><dt>Pior queda</dt><dd className={tom(c.drawdown_maximo)}>{pct(c.drawdown_maximo)}</dd></div>
                <div><dt>Dias no positivo</dt><dd>{c.dias_positivos_pct == null ? "—" : `${Math.round(c.dias_positivos_pct * 100)}%`}</dd></div>
              </dl>
            </article>
          );
        })}
      </div>
      <p className="f-nota">
        <Icone nome="info" tamanho={14} /> Atenção: a Estratégia QUANT fica em média {pct(est.exposicao_media, false)} investida
        e o resto parado em caixa; o Ibovespa fica 100% investido. Oscilação baixa aqui vem principalmente de estar pouco
        investido — um colchão também não oscila. Para comparar habilidade, olhe a diferença de rendimento, não só a oscilação.
      </p>
      {rendaFixa ? (
        // O texto vai num único <span>: a nota é flexível e cada trecho viraria uma coluna.
        <p className="f-nota">
          <Icone nome="info" tamanho={14} />
          <span>
            Na simulação, o caixa da estratégia rende 0%. Deixar tudo no CDI teria
            rendido {pct(rendaFixa.retorno_acumulado)} no mesmo período: a estratégia está{" "}
            <strong className={tom(est.retorno_acumulado - rendaFixa.retorno_acumulado)}>
              {formatarNumero(Math.abs(est.retorno_acumulado - rendaFixa.retorno_acumulado) * 100, 2)} pontos percentuais
              {est.retorno_acumulado >= rendaFixa.retorno_acumulado ? " acima" : " abaixo"}
            </strong>{" "}
            da renda fixa.
          </span>
        </p>
      ) : d.cdi_indisponivel && (
        <p className="f-nota"><Icone nome="info" tamanho={14} /> <span>{d.cdi_indisponivel}</span></p>
      )}
      {!!d.sensibilidade_custos?.length && (
        <p className="f-nota">
          <Icone nome="info" tamanho={14} />
          <span>
            E com custos? Os custos configurados estão zerados. Pagando por operação{" "}
            {d.sensibilidade_custos.map((s, i) => (
              <span key={s.custo}>
                {i ? (i === d.sensibilidade_custos.length - 1 ? " ou " : ", ") : ""}
                {formatarNumero(s.custo * 100, 2)}%, a estratégia teria rendido{" "}
                <strong className={tom(s.retorno_acumulado)}>{pct(s.retorno_acumulado)}</strong>
              </span>
            ))}
            .
          </span>
        </p>
      )}
    </section>
  );
}

/* -------------------------------------------------------------- ativos */
function CartaoAtivo({ a, oculto, saldo, fracao }) {
  const s = SITUACOES[a.situacao];
  const u = a.ultima_decisao;
  return (
    <article className="f-ativo">
      <header>
        <span className="f-ativo-logo" style={{ background: COR_TICKER[a.ticker] }}>{a.ticker.slice(0, 2)}</span>
        <div>
          <strong>{a.empresa}</strong>
          <small>{a.ticker}</small>
        </div>
        <span className={`etiqueta ${s.classe}`}>{s.texto}</span>
      </header>
      <div className="f-ativo-preco">
        <div>
          <span className="f-ativo-valor">{a.preco ? `R$ ${formatarPreco(a.preco)}` : "—"}</span>
          <small className={tom(a.variacao_dia)}>{pct(a.variacao_dia)} hoje</small>
        </div>
        <div className="f-ativo-mini">
          <Minigrafico pontos={a.minigrafico} largura={110} altura={38} />
          <small className={tom(a.variacao_30d)}>{pct(a.variacao_30d)} em 30 dias</small>
        </div>
      </div>
      {a.posicao && (
        <div className="f-ativo-caixa">
          Você tem <Dinheiro valor={a.posicao.valor} oculto={oculto} />{" "}
          <span className={tom(a.posicao.retorno)}>({pct(a.posicao.retorno)})</span>
          <small>comprou a R$ {formatarPreco(a.posicao.preco_entrada)} em {dia(a.posicao.entrada)}</small>
        </div>
      )}
      {a.situacao === "compra_agendada" && (
        <div className="f-ativo-caixa agendada">
          Compra no próximo fechamento, com até {Math.round(fracao * 100)}% do saldo
          (≈ <Dinheiro valor={saldo * fracao} oculto={oculto} casas={0} />).
        </div>
      )}
      {a.situacao === "venda_agendada" && (
        <div className="f-ativo-caixa agendada">
          {a.posicao ? "Venda de toda a posição no próximo fechamento." : "A regra mandou vender, mas não há posição."}
        </div>
      )}
      <div className="f-ativo-analise">
        <small className="sutil">Última notícia analisada</small>
        {u ? (
          <>
            <p>{u.resumo}</p>
            {/* O corte de linhas vai no texto, não na citação: senão o recuo mostra meia linha. */}
            {u.trecho_fonte && <blockquote><span className="f-ativo-trecho">“{u.trecho_fonte}”</span></blockquote>}
            <div className="f-ativo-chips">
              <EtiquetaSentimento classificacao={u.sentimento ? { sentimento: u.sentimento, probabilidade: u.probabilidade } : null} />
              <span className="sutil">→ regra:</span><EtiquetaDecisao decisao={u.decisao} />
            </div>
            <small className="sutil">{u.motivo}{u.url && <> · <a href={u.url} target="_blank" rel="noreferrer">ler notícia</a></>}</small>
          </>
        ) : <p className="sutil">Nenhuma notícia sobre {a.empresa} passou pela IA ainda.</p>}
      </div>
    </article>
  );
}

/* --------------------------------------------- rendimento e histórico */
function Rendimentos({ d }) {
  const operacoes = [...d.operacoes_encerradas, ...d.posicoes_abertas].sort((a, b) => a.entrada.localeCompare(b.entrada));
  const h = d.historico_regra;
  const [valor, setValor] = useState(1000);
  return (
    <div className="f-grade">
      <Cartao titulo="Rendimento de cada decisão" subtitulo="Barra verde: ganhou. Barra vermelha: perdeu." className="f-span-2">
        <Estado vazio={!operacoes.length} mensagemVazio="Nenhuma compra executada ainda.">
          <BarrasRendimento formatar={(v) => pct(v)}
            itens={operacoes.map((o) => ({
              valor: o.retorno, rotulo: o.ticker,
              detalhe: `${o.ticker}: comprou a R$ ${formatarPreco(o.preco_entrada)} em ${dia(o.entrada)}; ` +
                `${o.aberta ? "hoje" : `vendeu em ${dia(o.saida)}`} a R$ ${formatarPreco(o.preco_saida)}.`,
            }))} />
          <div className="f-ese">
            <label htmlFor="valor-simulado">E se eu tivesse colocado</label>
            <div className="campo-moeda">
              <span>R$</span>
              <input id="valor-simulado" type="number" min="0" step="100" value={valor}
                onChange={(e) => setValor(Math.max(0, Number(e.target.value) || 0))} />
            </div>
            <span className="sutil">em cada decisão?</span>
          </div>
          <ul className="f-lista">
            {operacoes.map((o, i) => (
              <li key={i}>
                <span className="f-ativo-logo pequeno" style={{ background: COR_TICKER[o.ticker] }}>{o.ticker.slice(0, 2)}</span>
                <div><strong>{o.ticker}</strong><small>{dia(o.entrada)} → {o.aberta ? "hoje" : dia(o.saida)}</small></div>
                <span className="sutil">{reais(valor, 2)} viraria</span>
                <strong className={tom(o.retorno)}>{reais(valor * (1 + o.retorno), 2)}</strong>
              </li>
            ))}
          </ul>
        </Estado>
      </Cartao>
      <Cartao titulo="Histórico da regra" subtitulo="O que já aconteceu — não é previsão">
        <dl className="f-numeros">
          <div><dt>Decisões</dt><dd>{h.n}</dd></div>
          <div><dt>Rendimento médio</dt><dd className={tom(h.media)}>{pct(h.media)}</dd></div>
          <div><dt>Acertos</dt><dd>{h.taxa_acerto == null ? "—" : `${Math.round(h.taxa_acerto * 100)}%`}</dd></div>
          <div><dt>Melhor / pior</dt><dd className="f-numeros-par">{pct(h.melhor)} <span className="sutil">/</span> {pct(h.pior)}</dd></div>
          <div className="largo">
            <dt>Margem de incerteza da média</dt>
            <dd>{h.intervalo_aproximado_95 ? `${pct(h.intervalo_aproximado_95[0])} a ${pct(h.intervalo_aproximado_95[1])}` : "precisa de 2 ou mais decisões"}</dd>
          </div>
        </dl>
        <p className="f-nota">Se essa margem incluir valores negativos, ainda não dá para dizer que a regra ganha dinheiro.</p>
      </Cartao>
    </div>
  );
}

/* ------------------------------------------------------ agenda e extrato */
function AgendaExtrato({ d, oculto }) {
  return (
    <div className="f-grade">
      <Cartao titulo="Próximas movimentações" subtitulo="Executam no fechamento do próximo pregão">
        <Estado vazio={!d.pendentes.length} mensagemVazio="Nada agendado.">
          <ul className="f-lista">
            {d.pendentes.map((p, i) => (
              <li key={i}>
                <span className={`f-estat-icone ${p.decisao === "compra" ? "tom-positivo" : "tom-negativo"}`}>
                  <Icone nome={p.decisao} tamanho={16} />
                </span>
                <div><strong>{p.decisao === "compra" ? "Comprar" : "Vender"} {p.ticker}</strong><small>notícia de {formatarData(p.publicado)}</small></div>
              </li>
            ))}
          </ul>
        </Estado>
      </Cartao>
      <Cartao titulo="Extrato" subtitulo="Todas as movimentações da carteira" className="f-span-2">
        <Estado vazio={!d.extrato.length} mensagemVazio="Nenhuma movimentação ainda.">
          <ul className="f-lista">
            {d.extrato.map((l, i) => (
              <li key={i}>
                <span className={`f-estat-icone ${l.tipo === "compra" ? "" : "tom-positivo"}`}>
                  <Icone nome={l.tipo} tamanho={16} />
                </span>
                <div>
                  <strong>{l.tipo === "compra" ? "Compra" : "Venda"} de {l.ticker}</strong>
                  <small>{dia(l.data)} · {formatarNumero(l.quantidade ?? l.valor / l.preco, 2)} ações a R$ {formatarPreco(l.preco)}</small>
                </div>
                <strong className={l.tipo === "compra" ? "" : tom(l.resultado)}>
                  {oculto ? "R$ ••••" : `${l.tipo === "compra" ? "−" : "+"}${reais(l.valor, 2)}`}
                </strong>
              </li>
            ))}
          </ul>
        </Estado>
        {!!d.ordens_ignoradas?.length && (
          <p className="f-nota"><Icone nome="info" tamanho={14} /> Não executadas: {d.ordens_ignoradas.map((o) => `${o.ticker} (${o.razao})`).join("; ")}.</p>
        )}
      </Cartao>
    </div>
  );
}

/* --------------------------------------------------------- como funciona */
function ComoFunciona({ d }) {
  const p = d.parametros;
  const passos = [
    ["noticias", "A IA lê a notícia", "Descobre a empresa, o tipo de evento, se é bom ou ruim e com que confiança — e mostra a frase que comprova."],
    ["escudo", "Uma regra fixa decide", `Compra se for confirmado, positivo, com confiança acima de ${formatarNumero(p.limiar_probabilidade, 2)} e sem notícia ruim da empresa nos ${p.janela_evento_recente_dias} dias anteriores.`],
    ["relogio", "Executa no dia seguinte", `No preço de fechamento real do próximo pregão, com até ${Math.round(p.max_posicao_pct * 100)}% do saldo por ação.`],
    ["grafico", "Você acompanha", "Saldo, produtos, ações e extrato — e decide se confia na estratégia."],
  ];
  return (
    <Cartao titulo="Como funciona">
      <ol className="f-passos">
        {passos.map(([icone, titulo, texto], i) => (
          <li key={titulo}>
            <span className="f-estat-icone"><Icone nome={icone} tamanho={18} /></span>
            <small>Passo {i + 1}</small>
            <strong>{titulo}</strong>
            <p>{texto}</p>
          </li>
        ))}
      </ol>
      <details className="f-detalhe">
        <summary>Por que não aparece "quanto vai render"?</summary>
        <p>Ninguém sabe quanto uma ação vai render, e o sistema não finge saber. Aqui você vê o que já aconteceu e a incerteza disso — é isso que permite julgar se a estratégia merece confiança.</p>
      </details>
      <details className="f-detalhe">
        <summary>Posso usar isso para decidir investir dinheiro real?</summary>
        <p>
          Use como um teste, não como garantia. Rendimento passado — ainda mais com dinheiro fictício e poucas semanas —
          não garante rendimento futuro. Observe o selo de maturidade: só com meses de histórico e dezenas de decisões os
          números começam a dizer algo. Isto não é recomendação de investimento.
          {!d.congelada && " Além disso, a regra ainda não foi congelada, então o resultado é exploratório."}
        </p>
      </details>
    </Cartao>
  );
}

/* ---------------------------------------------------------------- página */
export default function Simulacao({ base, irPara }) {
  const { dados: d, erro, carregando } = useApi(`/api/simulacao?base=${base}`);
  const [oculto, setOculto] = useState(false);

  return (
    <Estado carregando={carregando && !d} erro={erro}>
      {d && (
        <div className="f-pagina">
          <Resumo d={d} oculto={oculto} setOculto={setOculto} />
          <Atalhos irPara={irPara} />
          {d.maturidade && <Maturidade m={d.maturidade} />}
          {d.estado !== "ok" && (
            <div className="f-aviso">
              <Icone nome="info" tamanho={16} />
              <span>
                {d.mensagem} A carteira começa com {reais(d.capital_inicial)} fictícios, 100% em caixa.
                {d.estado === "sem_dados" && !VITRINE && (
                  <> <button className="botao-link" onClick={() => irPara("acoes")}>Rodar o pipeline agora →</button></>
                )}
              </span>
            </div>
          )}

          {d.estado === "ok" && (
            <>
              <div className="f-grade">
                <Evolucao d={d} />
                <Alocacao d={d} oculto={oculto} />
              </div>
              <Produtos d={d} oculto={oculto} />
            </>
          )}

          <section>
            <div className="f-secao">
              <h2>Ações acompanhadas</h2>
              <p>Preço real, situação na carteira e a última notícia que a IA analisou de cada empresa.</p>
            </div>
            <div className="f-ativos">
              {(d.ativos || []).map((a) => (
                <CartaoAtivo key={a.ticker} a={a} oculto={oculto}
                  saldo={d.carteiras?.estrategia.patrimonio ?? d.capital_inicial} fracao={d.parametros.max_posicao_pct} />
              ))}
            </div>
          </section>

          {d.estado === "ok" && <Rendimentos d={d} />}
          {d.estado === "ok" && <AgendaExtrato d={d} oculto={oculto} />}
          <ComoFunciona d={d} />
          <p className="f-rodape-aviso">{d.aviso}</p>
        </div>
      )}
    </Estado>
  );
}
