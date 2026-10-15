import { useEffect, useState } from "react";
import { useApi, formatarData } from "../api.js";
import { Cartao, Estado, EtiquetaDecisao, EtiquetaSentimento, Indicador } from "../ui.jsx";

function Detalhe({ base, data }) {
  const { dados, erro, carregando } = useApi(data ? `/api/execucoes/${data}?base=${base}` : null);
  if (!data) return <div className="vazio">Escolha uma execução.</div>;
  return (
    <Estado carregando={carregando} erro={erro}>
      {dados && (
        <div className="pilha">
          {dados.resumo && (
            <div className="indicadores">
              <Indicador rotulo="Coletados" valor={dados.resumo.coletados} />
              <Indicador rotulo="Novos no arquivo" valor={dados.resumo.novos_arquivados} />
              <Indicador rotulo="Eventos válidos" valor={dados.resumo.eventos_validos} />
              <Indicador rotulo="Operações" valor={dados.resumo.operacoes}
                tom={dados.resumo.operacoes ? "positivo" : "neutro"} />
            </div>
          )}

          <Cartao titulo="Decisões da regra">
            <Estado vazio={!dados.decisoes.length} mensagemVazio="Nenhum evento avaliado neste dia.">
              <div className="tabela-rolagem">
                <table>
                  <thead>
                    <tr><th>Ticker</th><th>Decisão</th><th>Classificação</th><th>Evento</th><th>Motivo (regra)</th></tr>
                  </thead>
                  <tbody>
                    {dados.decisoes.map(({ evento, decisao }) => (
                      <tr key={evento.id}>
                        <td><span className="ticker">{decisao.ticker}</span></td>
                        <td><EtiquetaDecisao decisao={decisao.decisao} /></td>
                        <td><EtiquetaSentimento classificacao={evento.classificacao} /></td>
                        <td>
                          <div>{evento.resumo}</div>
                          <blockquote>“{evento.trecho_fonte}”</blockquote>
                          <small className="sutil">{evento.tipo_evento} · {evento.confirmado ? "confirmado" : "não confirmado"} · {evento.modelo}</small>
                        </td>
                        <td className="motivo">{decisao.motivo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Estado>
          </Cartao>

          <Cartao titulo="Relatório do dia">
            {dados.relatorio ? <pre className="relatorio">{dados.relatorio}</pre> : <div className="vazio">Sem relatório.</div>}
          </Cartao>
        </div>
      )}
    </Estado>
  );
}

export default function Execucoes({ base }) {
  const { dados, erro, carregando, recarregar } = useApi(`/api/execucoes?base=${base}`);
  const [selecionada, setSelecionada] = useState(null);

  useEffect(() => {
    if (dados?.length && !dados.some((e) => e.data === selecionada)) setSelecionada(dados[0].data);
    if (dados && !dados.length) setSelecionada(null);
  }, [dados, selecionada]);

  return (
    <div className="mestre-detalhe">
      <Cartao titulo="Dias" acao={<button className="botao-link" onClick={recarregar}>Atualizar</button>}>
        <Estado carregando={carregando && !dados} erro={erro} vazio={dados && !dados.length}
          mensagemVazio="Nenhuma execução ainda.">
          <ul className="lista-dias">
            {dados?.map((e) => (
              <li key={e.data}>
                <button className={e.data === selecionada ? "ativo" : ""} onClick={() => setSelecionada(e.data)}>
                  <strong>{formatarData(e.data + "T12:00:00-03:00", false)}</strong>
                  <span className="sutil">
                    {e.resumo ? `${e.resumo.eventos_validos} eventos · ${e.resumo.operacoes} operações` : "sem resumo"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Estado>
      </Cartao>
      <Detalhe base={base} data={selecionada} />
    </div>
  );
}
