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

export function Estado({ carregando, erro, vazio, mensagemVazio = "Nada por aqui ainda.", children }) {
  if (erro) return <div className="aviso tom-negativo">Erro: {erro}</div>;
  if (carregando) return <div className="carregando"><span className="giro" /> Carregando…</div>;
  if (vazio) return <div className="vazio">{mensagemVazio}</div>;
  return children;
}
