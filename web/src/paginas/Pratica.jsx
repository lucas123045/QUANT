import { useState } from "react";
import { formatarNumero, formatarPreco, plural, useApi } from "../api.js";
import { Cartao, Secao, dia, pct, tom } from "../comum.jsx";
import GraficoPatrimonio, { reais } from "../GraficoPatrimonio.jsx";
import { COR_TICKER } from "../graficos.jsx";
import Icone from "../icones.jsx";
import { Criterios, Estado, NumeroAnimado } from "../ui.jsx";

const SERIES_PRATICA = [
  { chave: "pratica", nome: "Na prática (líquida de custos e IR)", cor: "var(--serie-1)" },
  { chave: "pesquisa", nome: "Carteira da pesquisa (regra pura)", cor: "var(--serie-2)" },
  { chave: "ibovespa", nome: "Ibovespa (comprar e segurar)", cor: "var(--serie-3)" },
  { chave: "cdi", nome: "Renda fixa (100% do CDI)", cor: "var(--serie-4)" },
];

const COLUNAS = [["pratica", "Na prática"], ["pesquisa", "Pesquisa"], ["ibovespa", "Ibovespa"], ["cdi", "CDI"]];

const num = (v, casas = 2) => {
  if (v === null || v === undefined) return "—";
  return formatarNumero(Math.abs(v) < 0.5 * 10 ** -casas ? 0 : v, casas);  // sem "-0"
};

/** Linhas da tabela de risco: [rótulo, chave, formatar, explicação]. */
const LINHAS_RISCO = [
  ["Retorno no período", "retorno_acumulado", (v) => pct(v), "Quanto o patrimônio variou desde o início."],
  ["Retorno ao ano", "retorno_anualizado", (v) => pct(v), "O retorno do período levado para um ano (só com 60+ pregões)."],
  ["Oscilação ao ano", "volatilidade_anualizada", (v) => pct(v, false), "Desvio-padrão dos retornos diários, anualizado."],
  ["Maior queda", "drawdown_maximo", (v) => pct(v), "Do pico ao vale: o pior momento de quem entrou no topo."],
  ["Retorno por risco (Sharpe)", "sharpe", (v) => num(v), "Quanto rendeu acima do CDI por unidade de oscilação. Acima de 1 é bom; abaixo de 0, perdeu para a renda fixa."],
  ["Sortino", "sortino", (v) => num(v), "Como o Sharpe, mas só as quedas contam como risco."],
  ["Beta", "beta", (v) => num(v), "Quanto a carteira acompanha o Ibovespa (1 = igual; 0 = nada)."],
  ["Acertos", "taxa_acerto", (v) => (v == null ? "—" : `${Math.round(v * 100)}%`), "Fração das operações com lucro."],
  ["Ganho médio / perda média", "payoff", (v) => num(v), "Payoff: quanto o ganho médio é maior que a perda média."],
  ["Fator de lucro", "fator_lucro", (v) => num(v), "Soma dos ganhos dividida pela soma das perdas (acima de 1: ganhou mais do que perdeu)."],
];

const MOTIVOS_SAIDA = {
  prazo: "Prazo", "perda máxima": "Perda máxima", "notícia negativa": "Notícia negativa",
};

function Resumo({ d }) {
  const e = d.efeitos;
  return (
    <div className="f-resumo cinco">
      <section className="f-saldo">
        <div className="f-saldo-topo"><span>Patrimônio na prática (líquido de imposto)</span></div>
        <NumeroAnimado valor={d.patrimonio} formatar={(v) => reais(v, 2)} className="f-saldo-valor" />
        <div className="f-saldo-rodape">
          <span className={tom(d.patrimonio - d.capital_inicial)}>{pct(d.patrimonio / d.capital_inicial - 1)} desde {dia(d.inicio)}</span>
          <span className="sutil">·</span>
          <span>{Math.round(d.exposicao_atual * 100)}% investido em ações, o resto rendendo CDI</span>
        </div>
      </section>
      <Efeito icone="dinheiro" rotulo="Rendimento do caixa (CDI)" valor={e.juros_caixa} />
      <Efeito icone="frasco" rotulo="Custos da B3 pagos" valor={-e.custos_pagos} />
      <Efeito icone="escudo" rotulo="Imposto de renda" valor={-e.imposto} />
      <Efeito icone="grafico" rotulo="Diferença para a carteira da pesquisa" valor={e.diferenca_para_pesquisa} />
    </div>
  );
}

function Efeito({ icone, rotulo, valor }) {
  return (
    <section className="f-estat">
      <span className="f-estat-icone"><Icone nome={icone} tamanho={18} /></span>
      <span className={`f-estat-valor ${tom(valor)}`}>{Math.abs(valor) < 0.005 ? reais(0, 2) : `${valor > 0 ? "+" : "−"}${reais(Math.abs(valor), 2)}`}</span>
      <span className="f-estat-rotulo">{rotulo}</span>
    </section>
  );
}

function TabelaRisco({ d }) {
  const m = d.metricas;
  const confiaveis = m.pratica?.anualizadas_confiaveis;
  return (
    <Cartao titulo="Risco e retorno, lado a lado" subtitulo="Medidas que um gestor olha antes de confiar numa estratégia" className="f-span-2">
      <div className="tabela-rolagem">
        <table className="tabela-risco">
          <thead>
            <tr><th scope="col">Medida</th>{COLUNAS.filter(([k]) => m[k]).map(([k, nome]) => <th key={k} scope="col">{nome}</th>)}</tr>
          </thead>
          <tbody>
            {LINHAS_RISCO.map(([rotulo, chave, formatar, explicacao]) => (
              <tr key={chave}>
                <th scope="row">{rotulo}<small>{explicacao}</small></th>
                {COLUNAS.filter(([k]) => m[k]).map(([k]) => (
                  <td key={k} className={["retorno_acumulado", "retorno_anualizado"].includes(chave) ? tom(m[k][chave]) : ""}>
                    {formatar(m[k][chave])}
                  </td>
                ))}
              </tr>
            ))}
            <tr>
              <th scope="row">Operações<small>Compras já encerradas ou abertas.</small></th>
              {COLUNAS.filter(([k]) => m[k]).map(([k]) => <td key={k}>{m[k].n_operacoes ?? "—"}</td>)}
            </tr>
          </tbody>
        </table>
      </div>
      {!confiaveis && (
        <p className="f-nota"><Icone nome="info" tamanho={14} />
          <span>Com {plural(m.pratica?.pregoes ?? 0, "pregão", "pregões")}, retorno ao ano, Sharpe e Sortino não são mostrados: anualizar poucos dias gera números sem sentido (mínimo de 60 pregões).</span>
        </p>
      )}
    </Cartao>
  );
}

function Posicoes({ d }) {
  const [aberto, setAberto] = useState(null);
  const todas = [...d.posicoes_abertas.map((o) => ({ ...o, chave: `a-${o.ticker}` })),
    ...d.operacoes_encerradas.map((o, i) => ({ ...o, chave: `e-${i}` })).reverse()];
  return (
    <Cartao titulo="Operações na prática" subtitulo="Tamanho pelo risco, limite de perda e prazo · toque para ver as checagens" className="f-span-2">
      <Estado vazio={!todas.length} mensagemVazio="Nenhuma compra executada ainda.">
        <ul className="f-lista">
          {todas.map((o) => (
            <li key={o.chave} className="expansivel">
              <button className="f-lista-linha" onClick={() => setAberto(aberto === o.chave ? null : o.chave)} aria-expanded={aberto === o.chave}>
                <span className="f-ativo-logo pequeno" style={{ background: COR_TICKER[o.ticker] }}>{o.ticker.slice(0, 2)}</span>
                <div>
                  <strong>{o.ticker} <span className="sutil">· {pct(o.peso, false, 1)} do patrimônio</span></strong>
                  <small>
                    {dia(o.entrada)} → {o.aberta ? `hoje (sai em até ${plural(o.pregoes_restantes, "pregão", "pregões")} ou abaixo de R$ ${formatarPreco(o.stop)})` : `${dia(o.saida)} · ${MOTIVOS_SAIDA[o.motivo_saida] || o.motivo_saida}`}
                  </small>
                </div>
                <strong className={tom(o.retorno)}>{pct(o.retorno)}</strong>
                <span className="seta">{aberto === o.chave ? "▾" : "▸"}</span>
              </button>
              {aberto === o.chave && (
                <div className="porque">
                  <p className="porque-execucao">
                    Comprou {reais(o.investido, 2)} de {o.ticker} a R$ {formatarPreco(o.preco_entrada)} no fechamento de {dia(o.entrada)}.
                    {o.aberta ? ` Vale hoje ${reais(o.valor, 2)} (já descontado o custo de venda).`
                      : ` Vendeu a R$ ${formatarPreco(o.preco_saida)} em ${dia(o.saida)}: ${o.detalhe_saida}. Resultado de ${reais(o.resultado, 2)}.`}
                  </p>
                  {o.origem?.resumo && <div><h4>A notícia</h4><p>{o.origem.resumo}</p></div>}
                  <div><h4>O que a prática conferiu</h4><Criterios criterios={o.checagens} /></div>
                </div>
              )}
            </li>
          ))}
        </ul>
      </Estado>
    </Cartao>
  );
}

function Descartados({ d }) {
  const [aberto, setAberto] = useState(null);
  return (
    <Cartao titulo="Decisões que a prática não seguiu" subtitulo="A regra mandou, mas uma checagem prática barrou">
      <Estado vazio={!d.descartados.length} mensagemVazio="Até agora, a prática seguiu todas as decisões da regra.">
        <ul className="f-lista">
          {d.descartados.map((x, i) => (
            <li key={i} className="expansivel">
              <button className="f-lista-linha" onClick={() => setAberto(aberto === i ? null : i)} aria-expanded={aberto === i}>
                <span className={`f-estat-icone ${x.decisao === "compra" ? "tom-positivo" : "tom-negativo"}`}><Icone nome={x.decisao} tamanho={16} /></span>
                <div><strong>{x.decisao === "compra" ? "Não comprou" : "Não vendeu"} {x.ticker}</strong><small>{dia(x.data)} · {x.razao}</small></div>
                <span className="seta">{aberto === i ? "▾" : "▸"}</span>
              </button>
              {aberto === i && (
                <div className="porque">
                  <p className="porque-execucao">{x.detalhe}.</p>
                  {x.origem?.resumo && <div><h4>A notícia</h4><p>{x.origem.resumo}</p></div>}
                  {!!x.checagens?.length && <div><h4>Checagens</h4><Criterios criterios={x.checagens} /></div>}
                </div>
              )}
            </li>
          ))}
        </ul>
      </Estado>
    </Cartao>
  );
}

function Imposto({ d }) {
  const ir = d.imposto_de_renda;
  return (
    <Cartao titulo="Imposto de renda" subtitulo={`${Math.round(ir.aliquota * 100)}% sobre o lucro do mês; isento se as vendas do mês não passarem de ${reais(ir.isencao_vendas_mes)}`}>
      <Estado vazio={!ir.meses.length} mensagemVazio="Nenhuma venda ainda: nada a apurar.">
        <ul className="f-lista">
          {ir.meses.map((m) => (
            <li key={m.mes}>
              <span className="f-estat-icone"><Icone nome="relogio" tamanho={16} /></span>
              <div>
                <strong>{m.mes.split("-").reverse().join("/")}</strong>
                <small>vendas de {reais(m.vendas, 2)} · lucro de {reais(m.lucro, 2)} · {m.situacao}{m.vencimento_darf ? ` · DARF até ${dia(m.vencimento_darf)}` : ""}</small>
              </div>
              <strong className={m.imposto ? "tom-texto-negativo" : ""}>{reais(m.imposto, 2)}</strong>
            </li>
          ))}
        </ul>
        {ir.prejuizo_a_compensar > 0 && <p className="f-nota">Prejuízo acumulado a compensar: {reais(ir.prejuizo_a_compensar, 2)}.</p>}
      </Estado>
      <p className="f-nota"><Icone nome="info" tamanho={14} />
        <span>Prejuízo acumulado abate lucro tributável dos meses seguintes (interpretação da calculadora da Receita e da B3). Confirme com um contador antes de declarar.</span>
      </p>
    </Cartao>
  );
}

function Correlacoes({ c }) {
  if (!c?.matriz) return null;
  return (
    <Cartao titulo="Quanto as ações andam juntas" subtitulo={`Correlação dos retornos diários nos últimos ${c.pregoes} pregões (1 = sempre juntas)`}>
      <div className="tabela-rolagem">
        <table className="tabela-correlacao">
          <thead><tr><th />{c.tickers.map((t) => <th key={t} scope="col">{t}</th>)}</tr></thead>
          <tbody>
            {c.tickers.map((a, i) => (
              <tr key={a}>
                <th scope="row">{a}</th>
                {c.matriz[i].map((v, j) => (
                  <td key={j} style={{ "--intensidade": i === j || v == null ? 0 : Math.max(0, v) }}>{i === j ? "—" : num(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="f-nota">Duas ações com correlação alta são quase a mesma aposta: por isso o limite por setor.</p>
    </Cartao>
  );
}

function Regras({ p }) {
  const itens = [
    ["escudo", "Confirmação pelo mercado", `Não compra se, antes da execução, a ação já reagiu com força contra a notícia (mais de ${num(p.z_reacao, 0)} desvios além do Ibovespa): o mercado leu como surpresa ruim. Reação forte a favor não barra: movimentos de notícia tendem a continuar.`],
    ["noticias", "Surpresa no texto", "Não compra se o próprio texto diz que o número veio abaixo do esperado (e não vende se diz que veio acima)."],
    ["grafico", "Tamanho pelo risco", `Até ${Math.round(p.max_posicao * 100)}% por ação, menos para as que oscilam mais que ${Math.round(p.vol_referencia_anual * 100)}% ao ano: cada posição pesa o mesmo risco.`],
    ["painel", "Limite por setor", `No máximo ${Math.round(p.limite_setor * 100)}% do patrimônio num setor (Itaú e Bradesco contam juntos).`],
    ["relogio", "Saída por prazo e por perda", `Vende em ${p.prazo_maximo_pregoes} pregões, ou antes se a perda passar de ${num(p.stop_desvios, 0)} desvios do esperado no período.`],
    ["dinheiro", "Custos, imposto e caixa", `Custo da B3 de ${pct(p.custo_por_lado, false, 3)} por operação (leilão de fechamento), IR de ${Math.round(p.ir_aliquota * 100)}% e o dinheiro parado rendendo CDI.`],
  ];
  return (
    <Cartao titulo="Como a prática opera" subtitulo="As decisões são as da regra; isto é o que muda na execução">
      <ol className="f-passos tres">
        {itens.map(([icone, titulo, texto]) => (
          <li key={titulo}><span className="f-estat-icone"><Icone nome={icone} tamanho={18} /></span><strong>{titulo}</strong><p>{texto}</p></li>
        ))}
      </ol>
    </Cartao>
  );
}

export default function Pratica({ base }) {
  const { dados: d, erro, carregando } = useApi(`/api/pratica?base=${base}`);
  return (
    <Estado carregando={carregando && !d} erro={erro}>
      {d && (
        <div className="f-pagina">
          <div className="f-aviso">
            <Icone nome="info" tamanho={16} />
            <span>
              As <strong>mesmas decisões</strong> da regra, operadas como um investidor de verdade operaria: com custos, imposto,
              tamanho pelo risco e regra de saída. A carteira da pesquisa continua igual na página Minha carteira.
            </span>
          </div>
          {d.estado !== "ok" ? (
            <div className="f-aviso"><Icone nome="relogio" tamanho={16} /><span>{d.mensagem}</span></div>
          ) : (
            <>
              <Resumo d={d} />
              {d.cdi_indisponivel && <p className="f-nota"><Icone nome="info" tamanho={14} /> <span>{d.cdi_indisponivel}</span></p>}
              <div className="f-grade">
                <Cartao titulo="Prática × pesquisa × mercado" subtitulo="Todas começam com o mesmo valor" className="f-span-2">
                  <GraficoPatrimonio serie={d.serie} capital={d.capital_inicial} series={SERIES_PRATICA} />
                </Cartao>
                <Descartados d={d} />
              </div>
              <div className="f-grade">
                <TabelaRisco d={d} />
                <Correlacoes c={d.correlacoes} />
              </div>
              <div className="f-grade">
                <Posicoes d={d} />
                <Imposto d={d} />
              </div>
            </>
          )}
          <Secao titulo="Regras da prática" texto="Nenhuma delas altera a regra congelada da pesquisa." />
          <Regras p={d.parametros} />
          <p className="f-rodape-aviso">{d.aviso}</p>
        </div>
      )}
    </Estado>
  );
}
