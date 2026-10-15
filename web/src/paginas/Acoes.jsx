import { useEffect, useRef, useState } from "react";
import { MENSAGEM_VITRINE, VITRINE, pedir, useApi, formatarData } from "../api.js";
import { Cartao, Etiqueta } from "../ui.jsx";

const ACOES = [
  {
    tipo: "coletar",
    titulo: "Coletar notícias",
    descricao: "Lê os feeds RSS (InfoMoney e Money Times) e arquiva o que é novo. Usa a internet, não usa o LLM e não tem custo.",
    rotulo: "Coletar agora",
  },
  {
    tipo: "pipeline_teste",
    titulo: "Pipeline em modo de teste",
    descricao: "Fluxo completo com notícias de exemplo e LLM falso. Sem internet e sem custo. Grava em data/teste/.",
    rotulo: "Rodar teste",
  },
  {
    tipo: "pipeline_real",
    titulo: "Pipeline real",
    descricao: "Coleta, arquiva, extrai e classifica com o LLM configurado, decide pela regra e registra. Gera chamadas pagas ao provedor.",
    rotulo: "Rodar pipeline real",
    confirmar: "O pipeline real faz chamadas pagas ao LLM para cada notícia que menciona a carteira. Continuar?",
    destaque: true,
  },
];

const TONS_ESTADO = { executando: "alerta", concluida: "positivo", erro: "negativo" };
const NOMES_TIPO = Object.fromEntries(ACOES.map((a) => [a.tipo, a.titulo]));

export default function Acoes() {
  const [tarefa, setTarefa] = useState(null);
  const [erro, setErro] = useState(null);
  const historico = useApi("/api/tarefas");
  const terminal = useRef(null);

  useEffect(() => {
    if (tarefa?.estado !== "executando") return undefined;
    const intervalo = setInterval(() => {
      pedir(`/api/tarefas/${tarefa.id}`).then((t) => {
        setTarefa(t);
        if (t.estado !== "executando") historico.recarregar();
      }).catch(() => {});
    }, 1000);
    return () => clearInterval(intervalo);
  }, [tarefa?.id, tarefa?.estado]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (terminal.current) terminal.current.scrollTop = terminal.current.scrollHeight;
  }, [tarefa?.logs?.length]);

  async function iniciar(acao) {
    if (acao.confirmar && !window.confirm(acao.confirmar)) return;
    setErro(null);
    try {
      setTarefa(await pedir("/api/tarefas", { method: "POST", body: JSON.stringify({ tipo: acao.tipo }) }));
    } catch (e) {
      setErro(e.message);
    }
  }

  const ocupado = tarefa?.estado === "executando";

  return (
    <div className="pilha">
      {VITRINE && <div className="aviso tom-alerta">{MENSAGEM_VITRINE}</div>}
      <div className="acoes">
        {ACOES.map((a) => (
          <Cartao key={a.tipo} titulo={a.titulo} className={a.destaque ? "destaque" : ""}>
            <p className="nota">{a.descricao}</p>
            <button className={`botao ${a.destaque ? "primario" : ""}`} disabled={ocupado || VITRINE} onClick={() => iniciar(a)}>
              {ocupado && tarefa.tipo === a.tipo ? "Executando…" : a.rotulo}
            </button>
          </Cartao>
        ))}
        <Cartao titulo="Backtest">
          <p className="nota">
            Bloqueado: os períodos de treino, validação e teste estão pendentes de aprovação, e o período de
            teste também exige a data de congelamento da regra.
          </p>
          <button className="botao" disabled>Indisponível</button>
        </Cartao>
      </div>

      {erro && <div className="aviso tom-negativo">{erro}</div>}

      {tarefa && (
        <Cartao titulo={NOMES_TIPO[tarefa.tipo]}
          acao={<Etiqueta tom={TONS_ESTADO[tarefa.estado]}>{tarefa.estado}</Etiqueta>}>
          <pre className="console" ref={terminal}>
            {tarefa.logs.length ? tarefa.logs.join("\n") : "Aguardando saída…"}
          </pre>
          {tarefa.erro && <div className="aviso tom-negativo">{tarefa.erro}</div>}
          {tarefa.resultado && (
            <dl className="lista-chave-valor">
              {Object.entries(tarefa.resultado).map(([k, v]) => (
                <div key={k} className="par"><dt>{k.replaceAll("_", " ")}</dt><dd>{String(v)}</dd></div>
              ))}
            </dl>
          )}
        </Cartao>
      )}

      <Cartao titulo="Histórico desta sessão">
        {historico.dados?.length ? (
          <ul className="historico">
            {historico.dados.map((t) => (
              <li key={t.id}>
                <span>{formatarData(t.inicio)}</span>
                <span>{NOMES_TIPO[t.tipo]}</span>
                <Etiqueta tom={TONS_ESTADO[t.estado]}>{t.estado}</Etiqueta>
              </li>
            ))}
          </ul>
        ) : <div className="vazio">Nenhuma ação executada desde que a API subiu.</div>}
      </Cartao>
    </div>
  );
}
