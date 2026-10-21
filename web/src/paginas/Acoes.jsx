import { useEffect, useRef, useState } from "react";
import { VITRINE, estadoNuvem, pedir, rodarNaNuvem, useApi, formatarData } from "../api.js";
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

// ------------------------------------------------------------ versão online
const ACOES_NUVEM = [
  {
    tarefa: "coleta",
    titulo: "Coletar notícias",
    descricao: "Lê os feeds RSS dos portais e arquiva o que é novo. Não usa a IA e não tem custo.",
    rotulo: "Coletar agora",
  },
  {
    tarefa: "pipeline",
    titulo: "Pipeline real",
    descricao: "Coleta, a IA lê e classifica as notícias novas, a regra decide, a carteira simulada é atualizada e cada decisão é justificada. Gera chamadas pagas à OpenAI.",
    rotulo: "Rodar pipeline real",
    confirmar: "O pipeline real faz chamadas pagas à IA para cada notícia nova que menciona a carteira. Continuar?",
    destaque: true,
  },
];

function situacao(execucao) {
  if (execucao.status === "queued" || execucao.status === "waiting" || execucao.status === "pending") return ["Na fila", "alerta"];
  if (execucao.status !== "completed") return ["Rodando", "alerta"];
  if (execucao.conclusao === "success") return ["Concluída", "positivo"];
  if (execucao.conclusao === "cancelled" || execucao.conclusao === "skipped") return ["Cancelada", "neutro"];
  return ["Falhou", "negativo"];
}

function lerSenha() {
  try { return sessionStorage.getItem("quant.senha") || ""; } catch { return ""; }
}

/**
 * Site online: os botões pedem ao GitHub Actions para rodar o QUANT de verdade
 * (api/nuvem.js). O resultado vai para o ramo "dados", que o site lê.
 */
function AcoesNuvem() {
  const [estado, setEstado] = useState(null);
  const [erro, setErro] = useState(null);
  const [senha, setSenha] = useState(lerSenha);
  const [pedido, setPedido] = useState(null);  // {tarefa, quando}: pedido feito nesta visita
  const [enviando, setEnviando] = useState(null);

  const carregar = () => estadoNuvem().then((e) => { setEstado(e); setErro(null); })
    .catch((e) => setErro(`Não foi possível consultar a nuvem: ${e.message}`));
  useEffect(() => { carregar(); }, []);

  const execucoes = estado?.execucoes || [];
  const emAndamento = execucoes.some((e) => e.status !== "completed");
  // A execução que este pedido gerou (o GitHub leva alguns segundos para criá-la).
  const minha = pedido && execucoes.find((e) => e.evento === "workflow_dispatch"
    && new Date(e.inicio).getTime() >= pedido.quando - 15000);
  const aguardando = Boolean(pedido) && (!minha || minha.status !== "completed");

  useEffect(() => {
    if (!emAndamento && !aguardando) return undefined;
    const id = setInterval(carregar, 5000);
    return () => clearInterval(id);
  }, [emAndamento, aguardando]);

  async function rodar(acao) {
    if (!senha) { setErro("Digite a senha para rodar."); return; }
    if (acao.confirmar && !window.confirm(acao.confirmar)) return;
    setErro(null);
    setEnviando(acao.tarefa);
    try {
      await rodarNaNuvem(senha, acao.tarefa);
      try { sessionStorage.setItem("quant.senha", senha); } catch { /* sem armazenamento */ }
      setPedido({ tarefa: acao.tarefa, quando: Date.now() });
      setTimeout(carregar, 3000);
    } catch (e) {
      setErro(e.message);
    } finally {
      setEnviando(null);
    }
  }

  const ocupado = Boolean(enviando) || aguardando;
  const [rotuloMinha, tomMinha] = minha ? situacao(minha) : ["Enviado ao GitHub", "alerta"];

  return (
    <div className="pilha">
      <div className="aviso tom-alerta">
        O QUANT roda nos servidores do GitHub (de graça e com o histórico guardado). Sozinho, ele roda a cada 30 minutos;
        aqui você manda rodar agora. Leva de 1 a 4 minutos, e o resultado aparece no site quando termina.
      </div>
      {estado && !estado.configurado && (
        <div className="aviso tom-negativo">
          O botão ainda não foi ligado no Vercel: faltam as variáveis QUANT_SENHA e QUANT_GITHUB_TOKEN
          (Vercel → Settings → Environment Variables). A coleta automática a cada 30 minutos funciona mesmo assim.
        </div>
      )}

      <div className="filtros nuvem-senha">
        <input type="password" placeholder="Senha para rodar" value={senha} autoComplete="current-password"
          aria-label="Senha para rodar" onChange={(e) => setSenha(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") rodar(ACOES_NUVEM[1]); }} />
      </div>

      <div className="acoes">
        {ACOES_NUVEM.map((a) => (
          <Cartao key={a.tarefa} titulo={a.titulo} className={a.destaque ? "destaque" : ""}>
            <p className="nota">{a.descricao}</p>
            <button className={`botao ${a.destaque ? "primario" : ""}`} disabled={ocupado || estado?.configurado === false}
              onClick={() => rodar(a)}>
              {enviando === a.tarefa ? "Enviando…" : aguardando && pedido.tarefa === a.tarefa ? "Rodando na nuvem…" : a.rotulo}
            </button>
          </Cartao>
        ))}
      </div>

      {erro && <div className="aviso tom-negativo">{erro}</div>}

      {pedido && (
        <Cartao titulo={`Seu pedido: ${pedido.tarefa === "coleta" ? "coletar notícias" : "pipeline real"}`}
          acao={<Etiqueta tom={tomMinha}>{rotuloMinha}</Etiqueta>}>
          {minha?.status === "completed" ? (
            minha.conclusao === "success" ? (
              <div className="nuvem-pronto">
                <span>Pronto. Atualize o site para ver as notícias, as análises e as decisões novas.</span>
                <button className="botao primario" onClick={() => window.location.reload()}>Atualizar o site</button>
              </div>
            ) : (
              <p className="nota">Não terminou bem. <a href={minha.url} target="_blank" rel="noreferrer">Veja o log no GitHub</a>.</p>
            )
          ) : (
            <p className="nota">
              {minha ? "O GitHub está rodando o QUANT" : "Esperando o GitHub começar"}…
              {minha && <> (<a href={minha.url} target="_blank" rel="noreferrer">acompanhar ao vivo</a>)</>}
            </p>
          )}
        </Cartao>
      )}

      <Cartao titulo="Execuções na nuvem">
        {execucoes.length ? (
          <ul className="historico">
            {execucoes.map((e) => {
              const [rotulo, tom] = situacao(e);
              return (
                <li key={e.id}>
                  <span>{formatarData(e.inicio)}</span>
                  <span><a href={e.url} target="_blank" rel="noreferrer">{e.titulo}</a></span>
                  <Etiqueta tom={tom}>{rotulo}</Etiqueta>
                </li>
              );
            })}
          </ul>
        ) : <div className="vazio">{estado ? "Nenhuma execução na nuvem ainda." : "Consultando…"}</div>}
      </Cartao>
    </div>
  );
}

export default function Acoes() {
  return VITRINE ? <AcoesNuvem /> : <AcoesLocais />;
}

function AcoesLocais() {
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
      <div className="acoes">
        {ACOES.map((a) => (
          <Cartao key={a.tipo} titulo={a.titulo} className={a.destaque ? "destaque" : ""}>
            <p className="nota">{a.descricao}</p>
            <button className={`botao ${a.destaque ? "primario" : ""}`} disabled={ocupado} onClick={() => iniciar(a)}>
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
