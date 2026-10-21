import { useEffect, useRef, useState } from "react";

/** Quem pede menos movimento no sistema operacional vê tudo estático. */
export function semMovimento() {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
}

/** Valor que "conta" até o alvo (suaviza no fim), como num painel de mercado. */
export function useNumeroAnimado(alvo, duracao = 900) {
  const animar = Number.isFinite(alvo) && !semMovimento();
  const [valor, setValor] = useState(animar ? 0 : alvo);
  const atual = useRef(animar ? 0 : alvo);
  useEffect(() => {
    if (!Number.isFinite(alvo) || semMovimento()) {
      atual.current = alvo;
      setValor(alvo);
      return undefined;
    }
    const inicio = Number.isFinite(atual.current) ? atual.current : 0;
    const t0 = performance.now();
    let quadro;
    const passo = (agora) => {
      const p = Math.min(1, (agora - t0) / duracao);
      const v = inicio + (alvo - inicio) * (1 - (1 - p) ** 3);
      atual.current = v;
      setValor(v);
      if (p < 1) quadro = requestAnimationFrame(passo);
    };
    quadro = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(quadro);
  }, [alvo, duracao]);
  return valor;
}

/**
 * Número animado: conta até o valor ao aparecer e, quando o valor muda numa
 * atualização automática, pisca verde (subiu) ou vermelho (caiu).
 */
export function NumeroAnimado({ valor, formatar, className = "" }) {
  const animado = useNumeroAnimado(valor);
  const anterior = useRef(valor);
  const [piscar, setPiscar] = useState("");
  useEffect(() => {
    const antes = anterior.current;
    anterior.current = valor;
    if (!Number.isFinite(antes) || !Number.isFinite(valor) || antes === valor) return undefined;
    setPiscar(valor > antes ? "piscar-sobe" : "piscar-desce");
    const id = setTimeout(() => setPiscar(""), 1400);
    return () => clearTimeout(id);
  }, [valor]);
  return <span className={`numero-animado ${piscar} ${className}`}>{formatar(animado)}</span>;
}

/** Placeholder brilhante enquanto os dados chegam (no lugar de "carregando"). */
export function Esqueleto({ linhas = 3 }) {
  return (
    <div className="esqueleto" role="status" aria-label="carregando">
      {Array.from({ length: linhas }, (_, i) => <span key={i} style={{ width: `${92 - i * 17}%` }} />)}
    </div>
  );
}

export function Cartao({ titulo, acao, children, className = "" }) {
  return (
    <section className={`cartao ${className}`}>
      {(titulo || acao) && (
        <header className="cartao-topo">
          {titulo && <h2>{titulo}</h2>}
          {acao}
        </header>
      )}
      {children}
    </section>
  );
}

export function Indicador({ rotulo, valor, detalhe, tom = "neutro" }) {
  return (
    <div className={`indicador tom-${tom}`}>
      <span className="indicador-rotulo">{rotulo}</span>
      <strong className="indicador-valor">{valor}</strong>
      {detalhe && <span className="indicador-detalhe">{detalhe}</span>}
    </div>
  );
}

const TONS_DECISAO = { compra: "positivo", venda: "negativo", manter: "neutro" };
const TONS_SENTIMENTO = { positivo: "positivo", negativo: "negativo", neutro: "neutro" };

export function Etiqueta({ children, tom = "neutro" }) {
  return <span className={`etiqueta tom-${tom}`}>{children}</span>;
}

export function EtiquetaDecisao({ decisao }) {
  return <Etiqueta tom={TONS_DECISAO[decisao] || "neutro"}>{decisao?.toUpperCase()}</Etiqueta>;
}

export function EtiquetaSentimento({ classificacao }) {
  if (!classificacao) return <Etiqueta>sem classificação</Etiqueta>;
  const { sentimento, probabilidade } = classificacao;
  return (
    <Etiqueta tom={TONS_SENTIMENTO[sentimento]}>
      {sentimento} · {Math.round(probabilidade * 100)}%
    </Etiqueta>
  );
}

export function Tickers({ lista }) {
  if (!lista?.length) return <span className="sutil">—</span>;
  return (
    <span className="tickers">
      {lista.map((t) => <span key={t} className="ticker">{t}</span>)}
    </span>
  );
}

/**
 * Justificativa passo a passo: cada condição da regra, conferida, com o valor
 * que decidiu. `criterios`: [{criterio, ok, detalhe}] gravado pela regra (V2+).
 */
export function Criterios({ criterios, versao }) {
  if (!criterios?.length) {
    return (
      <p className="criterios-vazio">
        {versao && versao !== "REGRA_V2"
          ? `Decisão da ${versao.replace("_", " ")}, anterior à revisão: não guardava a lista de critérios e não entra na carteira atual.`
          : "Sem a lista de critérios desta decisão."}
      </p>
    );
  }
  return (
    <ul className="criterios">
      {criterios.map((c, i) => (
        <li key={c.criterio} className={c.ok === true ? "ok" : c.ok === false ? "falhou" : "na"}
          style={{ "--ordem": i }}>
          <span className="criterios-marca" aria-label={c.ok === true ? "cumprido" : c.ok === false ? "não cumprido" : "não se aplica"}>
            {c.ok === true ? "✓" : c.ok === false ? "✗" : "–"}
          </span>
          <span>{c.criterio}<small>{c.detalhe}</small></span>
        </li>
      ))}
    </ul>
  );
}

export function Estado({ carregando, erro, vazio, mensagemVazio = "Sem registros.", children }) {
  if (erro) return <div className="aviso tom-negativo">Erro: {erro}</div>;
  if (carregando) return <Esqueleto />;
  if (vazio) return <div className="vazio">{mensagemVazio}</div>;
  return children;
}
