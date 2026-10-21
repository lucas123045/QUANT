// Peças comuns às páginas de finanças (Carteira, Na prática, Evidências, Mercado).
import { formatarData, formatarNumero } from "./api.js";

export const dia = (iso) => (iso ? formatarData(iso + "T12:00:00-03:00", false) : "—");

export const pct = (v, sinal = true, casas = 2) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (Math.abs(v) < 0.5 * 10 ** -(casas + 2)) return "0%";  // zero (ou quase) não leva sinal
  return `${sinal && v > 0 ? "+" : ""}${formatarNumero(v * 100, casas)}%`;
};

/** Classe de cor do texto pelo sinal do número. */
export const tom = (v) => (!v ? "" : v > 0 ? "tom-texto-positivo" : "tom-texto-negativo");

export function Cartao({ titulo, subtitulo, acao, children, className = "" }) {
  return (
    <section className={`f-cartao ${className}`}>
      {(titulo || acao) && (
        <header className="f-cartao-topo">
          <div>
            {titulo && <h2>{titulo}</h2>}
            {subtitulo && <p>{subtitulo}</p>}
          </div>
          {acao}
        </header>
      )}
      {children}
    </section>
  );
}

/** Cabeçalho de seção (título e uma linha de explicação). */
export function Secao({ titulo, texto }) {
  return (
    <div className="f-secao">
      <h2>{titulo}</h2>
      {texto && <p>{texto}</p>}
    </div>
  );
}
