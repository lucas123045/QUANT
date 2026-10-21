import { useState } from "react";
import { formatarNumero, plural, useApi } from "../api.js";
import { Cartao, Secao, dia, pct, tom } from "../comum.jsx";
import Icone from "../icones.jsx";
import { Estado, Etiqueta } from "../ui.jsx";

const JANELAS = [["reacao", "Antes da execução"], ["car_1", "1 pregão depois"], ["car_5", "5 pregões depois"], ["car_20", "20 pregões depois"]];
const TONS_LEITURA = { "a favor": "positivo", contra: "negativo", neutra: "neutro" };

/**
 * Intervalos de 95% de cada grupo em torno do zero: se a barra cruza o zero,
 * não há evidência de efeito (é o jeito honesto de mostrar amostra pequena).
 */
function Intervalos({ grupos, campo }) {
  const validos = grupos.filter((g) => g[campo].n >= 2 && g[campo].intervalo);
  if (!validos.length) return <div className="vazio">Ainda não há grupo com 2 ou mais eventos nesta janela.</div>;
  const limite = Math.max(0.005, ...validos.flatMap((g) => g[campo].intervalo.map(Math.abs)));
  const x = (v) => 50 + (v / limite) * 48;  // % da largura; zero no meio
  return (
    <ul className="intervalos">
      {validos.map((g) => {
        const [a, b] = g[campo].intervalo;
        const cruza = a < 0 && b > 0;
        return (
          <li key={g.grupo}>
            <span className="intervalos-rotulo">{g.grupo} <small>n = {g[campo].n}</small></span>
            <span className="intervalos-trilho" aria-label={`média ${pct(g[campo].media)}, de ${pct(a)} a ${pct(b)}`}>
              <span className="intervalos-zero" />
              <span className={`intervalos-barra ${cruza ? "cruza" : b <= 0 ? "contra" : "favor"}`}
                style={{ left: `${x(a)}%`, width: `${Math.max(0.6, x(b) - x(a))}%` }} />
              <span className="intervalos-media" style={{ left: `${x(g[campo].media)}%` }} />
            </span>
            <span className={`intervalos-valor ${tom(g[campo].media)}`}>{pct(g[campo].media)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Grupos({ e }) {
  const [janela, setJanela] = useState("car_5");
  return (
    <Cartao titulo="O preço anda a favor da classificação da IA?"
      subtitulo="Retorno além do Ibovespa (modelo de mercado), com o sinal da notícia: positivo = andou como a IA disse"
      className="f-span-2"
      acao={(
        <div className="f-segmentado" role="group" aria-label="Janela">
          {JANELAS.map(([k, nome]) => (
            <button key={k} className={janela === k ? "ativo" : ""} onClick={() => setJanela(k)}>{nome}</button>
          ))}
        </div>
      )}>
      <Intervalos grupos={e.grupos} campo={janela} />
      <p className="f-nota"><Icone nome="info" tamanho={14} />
        <span>Barra: intervalo de 95% da média; traço: a média. Se a barra cruza o zero (cinza), não dá para dizer que há efeito.
          "Antes da execução" é o que o mercado já andou antes de o QUANT poder agir.</span>
      </p>
    </Cartao>
  );
}

function Atraso({ e }) {
  const l = e.latencia;
  return (
    <Cartao titulo="A notícia chega tarde?" subtitulo="Atraso da coleta e o que já tinha acontecido no preço">
      <p className="evidencia-destaque">{e.leitura_atraso?.texto}</p>
      <dl className="f-numeros">
        {l.fontes.map((f) => (
          <div key={f.fonte}>
            <dt>{f.fonte}</dt>
            <dd>{formatarNumero(f.mediana_min, 0)} min <small className="sutil">(90% em até {formatarNumero(f.p90_min, 0)} min)</small></dd>
          </div>
        ))}
        <div><dt>Publicadas com a B3 aberta</dt><dd>{l.fracao_no_pregao == null ? "—" : `${Math.round(l.fracao_no_pregao * 100)}%`}</dd></div>
        {l.intervalo_mediano_coletas_min != null && (
          <div><dt>Intervalo entre coletas</dt><dd>{formatarNumero(l.intervalo_mediano_coletas_min, 0)} min</dd></div>
        )}
      </dl>
      <p className="f-nota"><Icone nome="info" tamanho={14} /><span>{l.nota}{l.fora_da_medida ? ` ${plural(l.fora_da_medida, "notícia arquivada", "notícias arquivadas")} em lote (primeira coleta ou computador desligado) ficaram fora da medida.` : ""}</span></p>
    </Cartao>
  );
}

function Calibracao({ c }) {
  return (
    <Cartao titulo="A confiança da IA é confiável?" subtitulo="Em cada faixa de confiança, quantas vezes a direção acertou em 5 pregões">
      <ul className="calibracao">
        {c.faixas.map((f) => (
          <li key={f.faixa[0]}>
            <span>{Math.round(f.faixa[0] * 100)}–{Math.round(f.faixa[1] * 100)}% <small>n = {f.n}</small></span>
            <span className="calibracao-barras">
              {f.n > 0 ? (
                <>
                  <span className="calibracao-declarada" style={{ width: `${f.confianca_media * 100}%` }} title="confiança declarada" />
                  <span className="calibracao-observada" style={{ width: `${f.taxa_acerto * 100}%` }} title="acerto observado" />
                </>
              ) : <small className="sutil">sem eventos nesta faixa</small>}
            </span>
            <span>{f.taxa_acerto == null ? "—" : `${Math.round(f.taxa_acerto * 100)}%`}</span>
          </li>
        ))}
      </ul>
      <div className="legenda">
        <span><span className="grafico-amostra" style={{ background: "var(--texto-3)" }} />Confiança declarada</span>
        <span><span className="grafico-amostra" style={{ background: "var(--acento)" }} />Acerto observado</span>
      </div>
      <p className="f-nota">{c.leitura}{c.brier != null ? ` Escore de Brier: ${formatarNumero(c.brier, 3)} (0 é perfeito; 0,25 é chutar 50%).` : ""}</p>
    </Cartao>
  );
}

function Observacoes({ e }) {
  const [todas, setTodas] = useState(false);
  const lista = todas ? e.observacoes : e.observacoes.slice(-12);
  return (
    <Cartao titulo="Eventos estudados" subtitulo="Um por empresa, dia e sentido (o mesmo fato em vários portais conta uma vez)" className="f-span-2">
      <Estado vazio={!e.observacoes.length} mensagemVazio="Nenhum evento ainda.">
        <div className="tabela-rolagem">
          <table className="tabela-eventos">
            <thead>
              <tr><th>Data</th><th>Ação</th><th>Evento</th><th>IA</th><th>Reação</th><th>1 pregão</th><th>5</th><th>20</th></tr>
            </thead>
            <tbody>
              {[...lista].reverse().map((o) => (
                <tr key={`${o.id}-${o.data}`}>
                  <td>{dia(o.data)}</td>
                  <td><strong>{o.ticker}</strong>{o.operado && <small className="tom-texto-positivo"> operado</small>}</td>
                  <td>
                    {o.url ? <a href={o.url} target="_blank" rel="noreferrer">{o.resumo}</a> : o.resumo}
                    <small>{o.tipo_evento}{o.confirmado ? "" : " · não confirmado"}{o.tipo_fonte === "fato_relevante" ? " · CVM" : ""}</small>
                  </td>
                  <td><Etiqueta tom={o.sentimento === "positivo" ? "positivo" : "negativo"}>{o.sentimento} · {Math.round((o.probabilidade ?? 0) * 100)}%</Etiqueta></td>
                  <td>{o.leitura_reacao ? <Etiqueta tom={TONS_LEITURA[o.leitura_reacao]}>{o.leitura_reacao}</Etiqueta> : "—"}</td>
                  {["car_1", "car_5", "car_20"].map((k) => <td key={k} className={tom(o[k])}>{o[k] == null ? "…" : pct(o[k])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {e.observacoes.length > 12 && (
          <button className="botao-link" onClick={() => setTodas(!todas)}>{todas ? "Mostrar só os recentes" : `Mostrar todos os ${e.observacoes.length}`}</button>
        )}
        <p className="f-nota">"…": a janela ainda não terminou. Retornos com o sinal da notícia: positivo quando o preço andou como a IA classificou.</p>
      </Estado>
    </Cartao>
  );
}

function Metodo({ m }) {
  return (
    <Cartao titulo="Como é medido">
      <details className="f-detalhe" open>
        <summary>Retorno anormal (modelo de mercado)</summary>
        <p>Para cada evento, estima quanto a ação costuma andar junto com o Ibovespa (o beta) nos {m.janela_estimacao} pregões antes da notícia.
          O retorno anormal é o que a ação andou além disso. Somado numa janela, vira o CAR.</p>
      </details>
      <details className="f-detalhe">
        <summary>As janelas</summary>
        <p>"Antes da execução": do fechamento anterior ao dia da notícia até o fechamento da véspera da execução, o que já tinha acontecido quando o QUANT
          podia agir. Depois: do fechamento de execução (primeiro pregão depois do dia da notícia) até {m.horizontes.join(", ")} pregões à frente.</p>
      </details>
      <details className="f-detalhe">
        <summary>Por que tanta cautela com poucos eventos</summary>
        <p>Com menos de {m.minimo_grupo} eventos, uma média de retornos de ações é quase só ruído. O intervalo de 95% mostra isso:
          quanto menor a amostra, mais larga a barra. Só uma barra que não cruza o zero, com amostra razoável, é evidência.</p>
      </details>
    </Cartao>
  );
}

export default function Evidencias({ base }) {
  const { dados: e, erro, carregando } = useApi(`/api/evidencias?base=${base}`);
  return (
    <Estado carregando={carregando && !e} erro={erro}>
      {e && (
        <div className="f-pagina">
          <div className="f-aviso">
            <Icone nome="info" tamanho={16} />
            <span>Aqui o QUANT se testa: o preço realmente reage às notícias que a IA classifica? A tempo de o sistema aproveitar?
              Nada nesta página muda as decisões; é evidência para julgar a estratégia.</span>
          </div>
          {e.estado !== "ok" ? (
            <div className="f-aviso"><Icone nome="relogio" tamanho={16} /><span>{e.mensagem}</span></div>
          ) : (
            <>
              <div className="f-grade">
                <Grupos e={e} />
                <Atraso e={e} />
              </div>
              <Secao titulo="Leitura por grupo" texto={`${plural(e.n_eventos, "evento estudado", "eventos estudados")} até o fechamento de ${dia(e.ultimo_fechamento)}.`} />
              <ul className="leituras">
                {e.grupos.filter((g) => g.n).map((g) => (
                  <li key={g.grupo}><strong>{g.grupo}</strong> <small className="sutil">({g.n})</small><span>{g.leitura}</span></li>
                ))}
              </ul>
              <div className="f-grade">
                <Calibracao c={e.calibracao} />
                <Observacoes e={e} />
              </div>
            </>
          )}
          <Metodo m={e.metodo} />
        </div>
      )}
    </Estado>
  );
}
