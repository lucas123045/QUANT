// Ícones de traço simples (24x24, cor do texto).
// Um texto = um caminho só. Uma lista = peças [classe, caminho, escreve?] que o CSS
// anima em separado (styles.css, "ícones da navegação"); "escreve" liga
// pathLength=1, para a linha poder ser traçada com stroke-dashoffset.
const CAMINHOS = {
  carteira: [
    ["moeda", "M12 1.6a1.7 1.7 0 1 0 0 3.4 1.7 1.7 0 0 0 0-3.4z"],
    ["corpo", "M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3M4 7.5V17a2 2 0 0 0 2 2h13a1 1 0 0 0 1-1v-3M4 7.5A1.5 1.5 0 0 0 5.5 9H19a1 1 0 0 1 1 1v3"],
    ["fecho", "M20 13h-3.5a1.5 1.5 0 0 0 0 3H20"],
  ],
  painel: [
    ["b1", "M4 4h7v7H4z"], ["b2", "M13 4h7v4h-7z"], ["b3", "M13 10h7v10h-7z"], ["b4", "M4 13h7v7H4z"],
  ],
  estudos: [
    ["livro", "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21zM4 5.5v13A2.5 2.5 0 0 1 6.5 16H20"],
    ["l1", "M8 7h8", true], ["l2", "M8 10h8", true], ["l3", "M8 13h5", true],
  ],
  noticias: [
    ["jornal", "M5 5h11v14H6a1 1 0 0 1-1-1zM16 9h3v9a1 1 0 0 1-1 1h-2"],
    ["l1", "M8 9h5", true], ["l2", "M8 12h5", true], ["l3", "M8 15h3", true],
  ],
  execucoes: [
    ["folha", "M5 6h14v13H5zM5 10h14"],
    ["argola", "M9 4v4M15 4v4"],
    ["d1", "M8.5 14h2"], ["d2", "M13.5 14h2"],
  ],
  operacoes: [["seta-a", "M7 7h12l-3-3"], ["seta-b", "M17 17H5l3 3"]],
  acoes: [["onda", "M8 5.5v13l10-6.5z"], ["play", "M8 5.5v13l10-6.5z"]],
  configuracao: [["engrenagem", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 13.5l1.4 1.1-2 3.4-1.7-.6a7 7 0 0 1-1.7 1l-.3 1.8h-4l-.3-1.8a7 7 0 0 1-1.7-1l-1.7.6-2-3.4 1.4-1.1a7 7 0 0 1 0-2l-1.4-1.1 2-3.4 1.7.6a7 7 0 0 1 1.7-1l.3-1.8h4l.3 1.8a7 7 0 0 1 1.7 1l1.7-.6 2 3.4-1.4 1.1a7 7 0 0 1 0 2z"]],
  sol: [
    ["nucleo", "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"],
    ["raios", "M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"],
  ],
  lua: [["lua", "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"]],
  olho: "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
  olhoFechado: "M3 3l18 18M10.6 6.1A9 9 0 0 1 12 6c6 0 9.5 6 9.5 6a16 16 0 0 1-2.6 3.3M6.6 7.4A16 16 0 0 0 2.5 12S6 18 12 18a9 9 0 0 0 4-.9",
  alta: "M4 16l5-5 4 4 7-7M15 8h5v5",
  dinheiro: "M3 7h18v10H3zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM6 10v4M18 10v4",
  grafico: "M4 20h16M6 16v-5M10 16V8M14 16v-7M18 16V5",
  escudo: "M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z",
  relogio: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 8v4l3 2",
  compra: "M12 19V5M6 11l6-6 6 6",
  venda: "M12 5v14M6 13l6 6 6-6",
  info: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 11v5M12 8h.01",
  frasco: "M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3M7.5 15h9",
};

export default function Icone({ nome, tamanho = 18, className = "" }) {
  const caminho = CAMINHOS[nome];
  return (
    <svg className={`icone icone-${nome} ${className}`} width={tamanho} height={tamanho} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true">
      {typeof caminho === "string" ? <path d={caminho} /> : caminho.map(([classe, d, escreve]) => (
        <path key={classe} className={`p-${classe}`} d={d} pathLength={escreve ? 1 : undefined} />
      ))}
    </svg>
  );
}
