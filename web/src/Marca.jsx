import { useId } from "react";

/**
 * Marca do QUANT: quadrado âmbar com barras e a seta de alta que sai do quadro.
 * O "recorte" escuro em volta da seta só existe dentro do quadrado (clipPath):
 * por fora, a seta fica limpa sobre qualquer fundo, nos dois temas.
 * Os mesmos desenhos estão em index.html (abertura) e nos ícones do app.
 */
export function LogoQuant({ tamanho = 36, className = "" }) {
  const id = useId().replace(/:/g, "");
  const seta = "M5 31.5l9.5-8.5 5 4.2L40 8";
  const ponta = "M31.5 7.5H40.5V16.5";
  return (
    <svg className={`logo-quant ${className}`} width={tamanho} height={tamanho} viewBox="0 0 48 48" aria-hidden="true">
      <defs>
        <linearGradient id={`logo-${id}`} x1="0" y1="0" x2="0.35" y2="1">
          <stop offset="0" stopColor="#ffcf33" />
          <stop offset="1" stopColor="#f59a0b" />
        </linearGradient>
        <clipPath id={`quadro-${id}`}><rect x="4" y="12" width="32" height="32" rx="9" /></clipPath>
      </defs>
      <g className="logo-quadro">
        <rect x="4" y="12" width="32" height="32" rx="9" fill={`url(#logo-${id})`} />
        <rect x="11" y="31" width="5.5" height="7.5" rx="1.2" fill="#0b0d0c" />
        <rect x="19.5" y="27" width="5.5" height="11.5" rx="1.2" fill="#0b0d0c" />
      </g>
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        <g clipPath={`url(#quadro-${id})`}>
          <path className="logo-recorte" d={seta} strokeWidth="9" pathLength="1" />
          <path className="logo-recorte" d={ponta} strokeWidth="9" pathLength="1" />
        </g>
        <path className="logo-seta" d={seta} stroke={`url(#logo-${id})`} strokeWidth="4.2" pathLength="1" />
        <path className="logo-seta logo-ponta" d={ponta} stroke="#ffcf33" strokeWidth="4.2" pathLength="1" />
      </g>
    </svg>
  );
}

/** "QUANT" com o A em âmbar e sem a barra do meio, como na logo. */
export function NomeQuant({ className = "" }) {
  return (
    <span className={`nome-quant ${className}`} role="img" aria-label="QUANT">
      <span aria-hidden="true">QU</span>
      <svg className="nome-quant-a" viewBox="0 0 12 14" aria-hidden="true">
        <polygon points="0,14 4.5,0 7.5,0 12,14 8.9,14 6,4.6 3.1,14" />
      </svg>
      <span aria-hidden="true">NT</span>
    </span>
  );
}
