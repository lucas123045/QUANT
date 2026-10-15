import { useApi, formatarData } from "../api.js";
import { Cartao, Estado, Indicador } from "../ui.jsx";

const ETAPAS_FUNIL = [
  ["noticias_arquivadas", "Notícias arquivadas"],
  ["noticias_com_mencao", "Mencionam a carteira"],
  ["eventos_extraidos", "Eventos extraídos"],
  ["eventos_confirmados", "Eventos confirmados"],
  ["eventos_acima_do_limiar", "Acima do limiar (0,7)"],
  ["operacoes", "Operações"],
];

function Funil({ funil }) {
  const maximo = Math.max(1, ...ETAPAS_FUNIL.map(([chave]) => funil[chave] || 0));
  return (
    <div className="funil">
      {ETAPAS_FUNIL.map(([chave, rotulo]) => {
        const valor = funil[chave] || 0;
        return (
          <div key={chave} className="funil-linha">
            <span className="funil-rotulo">{rotulo}</span>
            <div className="funil-trilho">
              <div className="funil-barra" style={{ width: `${(valor / maximo) * 100}%` }} />
            </div>
            <span className="funil-valor">{valor}</span>
          </div>
        );
      })}
    </div>
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
                {funil.dados.dias_de_coleta} dia(s) de coleta ·
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
