import { useState } from "react";
import { useApi, formatarData, formatarNumero, formatarPreco } from "../api.js";
import { Cartao, Estado, EtiquetaDecisao, Indicador } from "../ui.jsx";
import GraficoPatrimonio, { SERIES, reais } from "../GraficoPatrimonio.jsx";

function pct(valor) {
  if (valor === null || valor === undefined) return "—";
  return `${valor >= 0 ? "+" : ""}${formatarNumero(valor * 100, 2)}%`;
}

function tomRetorno(valor) {
  if (!valor) return "neutro";
  return valor > 0 ? "positivo" : "negativo";
}

function Origem({ origem }) {
  if (!origem) return null;
  return (
    <div className="origem">
      <div>{origem.resumo}</div>
      {origem.trecho_fonte && <blockquote>“{origem.trecho_fonte}”</blockquote>}
      <small className="sutil">
        {origem.fonte} · {formatarData(origem.publicado)}
        {origem.url && <> · <a href={origem.url} target="_blank" rel="noreferrer">notícia</a></>}
      </small>
    </div>
  );
}

function Calculadora({ operacoes }) {
  const [valor, setValor] = useState(1000);
  return (
    <Cartao titulo="E se eu tivesse aplicado…">
      <div className="calculadora-entrada">
        <label htmlFor="valor-simulado">Valor por decisão</label>
        <div className="campo-moeda">
          <span>R$</span>
          <input id="valor-simulado" type="number" min="0" step="100" value={valor}
            onChange={(e) => setValor(Math.max(0, Number(e.target.value) || 0))} />
        </div>
        <span className="nota">Mesma entrada e saída da carteira simulada, com o valor que você escolher.</span>
      </div>
      <Estado vazio={!operacoes.length} mensagemVazio="Nenhuma compra executada ainda.">
        <div className="tabela-rolagem">
          <table>
            <thead>
              <tr><th>Ação</th><th>Entrada</th><th className="num">Preço</th><th>Saída</th><th className="num">Preço</th>
                <th className="num">Retorno</th><th className="num">Aplicado</th><th className="num">Hoje / na saída</th><th>Notícia que originou</th></tr>
            </thead>
            <tbody>
              {operacoes.map((o, i) => (
                <tr key={`${o.ticker}-${o.entrada}-${i}`}>
                  <td><span className="ticker">{o.ticker}</span></td>
                  <td className="num">{formatarData(o.entrada + "T12:00:00-03:00", false)}</td>
                  <td className="num">{formatarPreco(o.preco_entrada)}</td>
                  <td className="num">{o.aberta ? <span className="etiqueta tom-alerta">aberta</span> : formatarData(o.saida + "T12:00:00-03:00", false)}</td>
                  <td className="num">{formatarPreco(o.preco_saida)}</td>
                  <td className={`num tom-texto-${tomRetorno(o.retorno)}`}>{pct(o.retorno)}</td>
                  <td className="num">{reais(valor, 2)}</td>
                  <td className={`num forte tom-texto-${tomRetorno(o.retorno)}`}>{reais(valor * (1 + o.retorno), 2)}</td>
                  <td><Origem origem={o.origem} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Estado>
    </Cartao>
  );
}

export default function Simulacao({ base }) {
  const { dados, erro, carregando, recarregar } = useApi(`/api/simulacao?base=${base}`);
  const d = dados;

  return (
    <Estado carregando={carregando && !d} erro={erro}>
      {d && (
        <div className="pilha">
          <div className={`aviso ${d.congelada ? "" : "tom-alerta"}`}>{d.aviso}</div>

          {d.estado !== "ok" ? (
            <Cartao titulo="Carteira simulada">
              <div className="vazio">{d.mensagem}</div>
              {!!d.pendentes?.length && <Pendentes pendentes={d.pendentes} />}
            </Cartao>
          ) : (
            <>
              <div className="indicadores">
                {SERIES.map((s) => {
                  const c = d.carteiras[s.chave];
                  return (
                    <Indicador key={s.chave} rotulo={s.nome.split(" (")[0]} valor={reais(c.patrimonio)}
                      detalhe={`${pct(c.retorno_acumulado)} desde ${formatarData(d.inicio + "T12:00:00-03:00", false)}`}
                      tom={tomRetorno(c.retorno_acumulado)} />
                  );
                })}
                <Indicador rotulo="Estratégia − Ibovespa"
                  valor={pct(d.carteiras.estrategia.retorno_acumulado - d.carteiras.ibovespa.retorno_acumulado)}
                  detalhe="diferença de retorno acumulado"
                  tom={tomRetorno(d.carteiras.estrategia.retorno_acumulado - d.carteiras.ibovespa.retorno_acumulado)} />
                <Indicador rotulo="Investido agora" valor={pct(d.carteiras.estrategia.caixa_investido_pct).replace("+", "")}
                  detalhe="do patrimônio da estratégia; o resto está em caixa" />
              </div>

              <Cartao titulo={`Patrimônio · capital inicial ${reais(d.capital_inicial)}`}
                acao={<button className="botao-link" onClick={recarregar}>Atualizar</button>}>
                <GraficoPatrimonio serie={d.serie} capital={d.capital_inicial} />
                <p className="nota">
                  Preços de fechamento reais (Yahoo Finance, ajustados por proventos) até {formatarData(d.ultimo_fechamento + "T12:00:00-03:00", false)}.
                  Cada decisão executa no fechamento do pregão seguinte à notícia. Custos por operação: {pct(d.custo_por_operacao).replace("+", "")}.
                </p>
              </Cartao>

              <Cartao titulo="Comparação">
                <div className="tabela-rolagem">
                  <table>
                    <thead>
                      <tr><th>Carteira</th><th className="num">Patrimônio</th><th className="num">Retorno</th>
                        <th className="num">Pior queda</th><th className="num">Operações</th><th className="num">Acerto</th>
                        <th className="num">Exposição média</th></tr>
                    </thead>
                    <tbody>
                      {SERIES.map((s) => {
                        const c = d.carteiras[s.chave];
                        return (
                          <tr key={s.chave}>
                            <td><span className="grafico-amostra" style={{ background: s.cor }} />{s.nome}</td>
                            <td className="num">{reais(c.patrimonio, 2)}</td>
                            <td className={`num tom-texto-${tomRetorno(c.retorno_acumulado)}`}>{pct(c.retorno_acumulado)}</td>
                            <td className="num">{pct(c.drawdown_maximo)}</td>
                            <td className="num">{c.n_operacoes ?? "—"}</td>
                            <td className="num">{c.taxa_acerto == null ? "—" : `${Math.round(c.taxa_acerto * 100)}%`}</td>
                            <td className="num">{c.exposicao_media == null ? "—" : `${Math.round(c.exposicao_media * 100)}%`}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="nota">
                  A estratégia investe no máximo 20% por ação e deixa o resto em caixa; o Ibovespa fica 100% investido.
                  Com poucos dias e poucas operações, a diferença entre as carteiras ainda é quase só ruído.
                </p>
              </Cartao>

              <Cartao titulo={`Posições abertas · ${d.posicoes_abertas.length}`}>
                <Estado vazio={!d.posicoes_abertas.length} mensagemVazio="Nenhuma posição aberta.">
                  <div className="tabela-rolagem">
                    <table>
                      <thead>
                        <tr><th>Ação</th><th>Desde</th><th className="num">Preço entrada</th><th className="num">Preço atual</th>
                          <th className="num">Investido</th><th className="num">Valor atual</th><th className="num">Resultado</th><th>Origem</th></tr>
                      </thead>
                      <tbody>
                        {d.posicoes_abertas.map((p) => (
                          <tr key={p.ticker}>
                            <td><span className="ticker">{p.ticker}</span></td>
                            <td className="num">{formatarData(p.entrada + "T12:00:00-03:00", false)} · {p.pregoes} preg.</td>
                            <td className="num">{formatarPreco(p.preco_entrada)}</td>
                            <td className="num">{formatarPreco(p.preco_saida)}</td>
                            <td className="num">{reais(p.investido, 2)}</td>
                            <td className="num">{reais(p.valor, 2)}</td>
                            <td className={`num forte tom-texto-${tomRetorno(p.resultado)}`}>{reais(p.resultado, 2)} ({pct(p.retorno)})</td>
                            <td><Origem origem={p.origem} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Estado>
              </Cartao>

              <Calculadora operacoes={[...d.posicoes_abertas, ...d.operacoes_encerradas]} />

              {!!d.pendentes.length && (
                <Cartao titulo={`Aguardando o próximo pregão · ${d.pendentes.length}`}><Pendentes pendentes={d.pendentes} /></Cartao>
              )}

              {!!d.ordens_ignoradas.length && (
                <Cartao titulo={`Ordens não executadas · ${d.ordens_ignoradas.length}`}>
                  <ul className="lista-simples">
                    {d.ordens_ignoradas.map((o, i) => (
                      <li key={i}>
                        <span className="ticker">{o.ticker}</span><EtiquetaDecisao decisao={o.decisao} />
                        <span className="sutil">{formatarData(o.data + "T12:00:00-03:00", false)}</span>
                        <span>{o.razao}</span>
                      </li>
                    ))}
                  </ul>
                </Cartao>
              )}
            </>
          )}
        </div>
      )}
    </Estado>
  );
}

function Pendentes({ pendentes }) {
  return (
    <ul className="lista-simples">
      {pendentes.map((p, i) => (
        <li key={i}>
          <span className="ticker">{p.ticker}</span><EtiquetaDecisao decisao={p.decisao} />
          <span className="sutil">notícia de {formatarData(p.publicado)}</span>
          <span>executa no fechamento do próximo pregão</span>
        </li>
      ))}
    </ul>
  );
}
