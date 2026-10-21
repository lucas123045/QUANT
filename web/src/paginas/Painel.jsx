import { useApi, formatarData, plural } from "../api.js";
import { Cartao, Criterios, Estado, Indicador } from "../ui.jsx";

/** Pré-requisitos do congelamento da regra: o que falta e como fazer (só o autor congela). */
function Congelamento() {
  const { dados: c, erro, carregando } = useApi("/api/congelamento");
  return (
    <Cartao titulo="Congelamento da regra" className="span-2">
      <Estado carregando={carregando && !c} erro={erro}>
        {c && (
          <>
            <p className="nota" style={{ marginTop: 0 }}>
              {c.congelada
                ? `Congelada em ${formatarData(c.data_congelamento + "T12:00:00-03:00", false)}.` +
                  (c.verificacao?.estado === "integra" ? " A regra em uso é a congelada." :
                    ` Atenção: ${(c.verificacao?.problemas || []).join("; ")}.`)
                : "Congelar fixa a regra, os prompts, os parâmetros e o modelo: daí em diante, o período de teste mede algo que não foi ajustado olhando o resultado. Quem congela é o autor."}
            </p>
            <Criterios criterios={c.itens.map((i) => ({ criterio: i.item, ok: i.ok, detalhe: i.acao ? `${i.detalhe}. ${i.acao}` : i.detalhe }))} />
            <p className="nota">
              Impressão digital da regra: <code>{c.impressao_digital.slice(0, 16)}…</code> (muda se o código, um prompt,
              um parâmetro ou as fontes mudarem).
              {!c.congelada && <> Com tudo cumprido: <code>{c.comando}</code>.</>}
            </p>
          </>
        )}
      </Estado>
    </Cartao>
  );
}

const ETAPAS_FUNIL = [
  ["noticias_arquivadas", "Notícias arquivadas"],
  ["noticias_com_mencao", "Mencionam a carteira"],
  ["eventos_extraidos", "Eventos extraídos"],
  ["eventos_confirmados", "Eventos confirmados"],
  ["eventos_relevantes", "Relevantes (materialidade)"],
  ["eventos_acima_do_limiar", "Acima do limiar"],
  ["operacoes", "Operações"],
];

function Funil({ funil }) {
  const maximo = Math.max(1, ...ETAPAS_FUNIL.map(([chave]) => funil[chave] || 0));
  return (
    <table className="funil">
      <thead>
        <tr><th>Etapa</th><th className="funil-col-barra" /><th className="num">Qtd.</th><th className="num">da anterior</th></tr>
      </thead>
      <tbody>
        {ETAPAS_FUNIL.map(([chave, rotulo], i) => {
          const valor = funil[chave] || 0;
          const anterior = i ? funil[ETAPAS_FUNIL[i - 1][0]] || 0 : null;
          const conversao = anterior ? `${Math.round((valor / anterior) * 100)}%` : "—";
          return (
            <tr key={chave}>
              <td>{chave === "eventos_acima_do_limiar" && funil.limiar_probabilidade != null
                ? `${rotulo} (${funil.limiar_probabilidade.toLocaleString("pt-BR")})` : rotulo}</td>
              <td className="funil-col-barra">
                <div className="funil-trilho">
                  <div className="funil-barra" style={{ width: `${(valor / maximo) * 100}%` }} />
                </div>
              </td>
              <td className="num forte">{valor}</td>
              <td className="num sutil">{conversao}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function Painel({ base, irPara }) {
  const status = useApi("/api/status");
  const funil = useApi(`/api/funil?base=${base}`);
  const execucoes = useApi(`/api/execucoes?base=${base}`);
  const s = status.dados;
  const ultima = execucoes.dados?.[0];

  return (
    <div className="grade">
      <Estado carregando={status.carregando && !s} erro={status.erro}>
        {s && (
          <div className="indicadores largura-total">
            <Indicador rotulo="Provedor de LLM" valor={s.provedor || "não definido"}
              detalhe={s.modelo || "configure o .env"} tom={s.provedor ? "positivo" : "alerta"} />
            <Indicador rotulo="Chave de API" valor={s.chave_configurada ? "Configurada" : "Ausente"}
              detalhe="lida do .env, nunca exibida" tom={s.chave_configurada ? "positivo" : "negativo"} />
            <Indicador rotulo="Períodos" valor={Object.values(s.periodos).every((p) => p) ? "Aprovados" : "Pendentes"}
              detalhe="backtest bloqueado até aprovar" tom={Object.values(s.periodos).every((p) => p) ? "positivo" : "alerta"} />
            <Indicador rotulo="Congelamento da regra" valor={s.data_congelamento || "Pendente"}
              detalhe="período de teste bloqueado" tom={s.data_congelamento ? "positivo" : "alerta"} />
            <Indicador rotulo="Corte do modelo" valor={s.data_corte_modelo || "Não registrado"}
              detalhe="risco de contaminação" tom={s.data_corte_modelo ? "positivo" : "alerta"} />
          </div>
        )}
      </Estado>

      <Cartao titulo="Funil" className="span-2"
        acao={<button className="botao-link" onClick={funil.recarregar}>Atualizar</button>}>
        <Estado carregando={funil.carregando && !funil.dados} erro={funil.erro}>
          {funil.dados && (
            <>
              <Funil funil={funil.dados} />
              <p className="nota">
                {plural(funil.dados.dias_de_coleta, "dia", "dias")} de coleta ·
                projeção: {funil.dados.projecao_operacoes_por_semestre ?? "—"} operações por semestre.
                {" "}{funil.dados.aviso}
              </p>
            </>
          )}
        </Estado>
      </Cartao>

      <Cartao titulo="Última execução"
        acao={<button className="botao-link" onClick={() => irPara("execucoes")}>Ver todas →</button>}>
        <Estado carregando={execucoes.carregando && !execucoes.dados} erro={execucoes.erro}
          vazio={!ultima} mensagemVazio="Nenhuma execução ainda. Use a página Ações.">
          {ultima?.resumo && (
            <dl className="lista-chave-valor">
              <dt>Data</dt><dd>{formatarData(ultima.data + "T12:00:00-03:00", false)}</dd>
              <dt>Coletados</dt><dd>{ultima.resumo.coletados}</dd>
              <dt>Novos no arquivo</dt><dd>{ultima.resumo.novos_arquivados}</dd>
              <dt>Eventos válidos</dt><dd>{ultima.resumo.eventos_validos}</dd>
              <dt>Operações</dt><dd>{ultima.resumo.operacoes}</dd>
              <dt>Backtest</dt><dd className="sutil">{ultima.resumo.backtest}</dd>
            </dl>
          )}
        </Estado>
      </Cartao>

      <Cartao titulo="Carteira provisória">
        {s && (
          <ul className="carteira">
            {s.carteira.map((c) => (
              <li key={c.ticker}><span className="ticker">{c.ticker}</span>{c.empresa}</li>
            ))}
          </ul>
        )}
        <p className="nota">Escolhida em 15/10/2026, sujeita a viés de sobrevivência.</p>
      </Cartao>

      {!!s?.alertas?.length && (
        <div className="largura-total pilha">
          {s.alertas.map((a) => <div key={a} className="aviso tom-alerta">{a}</div>)}
        </div>
      )}

      <Congelamento />

      <Cartao titulo="Pendências" className="span-2">
        {s && (
          <ul className="pendencias">
            {s.pendencias.map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
      </Cartao>
    </div>
  );
}
