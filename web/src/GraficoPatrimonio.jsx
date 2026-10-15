import { useEffect, useRef, useState } from "react";
import { formatarData } from "./api.js";

export const SERIES = [
  { chave: "estrategia", nome: "Estratégia (regra)", cor: "var(--serie-1)" },
  { chave: "baseline_1", nome: "Baseline 1 (toda notícia positiva)", cor: "var(--serie-2)" },
  { chave: "ibovespa", nome: "Ibovespa (comprar e segurar)", cor: "var(--serie-3)" },
];

const ALTURA = 300;
const MARGEM = { topo: 16, direita: 150, base: 30, esquerda: 78 };

export function reais(valor, casas = 0) {
  if (valor === null || valor === undefined) return "—";
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL",
    minimumFractionDigits: casas, maximumFractionDigits: casas });
}

/** Curva cúbica monótona: suaviza sem inventar picos ou vales entre os pontos reais. */
export function caminhoSuave(pontos) {
  if (pontos.length < 3) return `M${pontos.map((p) => p.join(",")).join(" L")}`;
  const n = pontos.length;
  const inclinacoes = [];
  for (let i = 0; i < n - 1; i++) {
    inclinacoes.push((pontos[i + 1][1] - pontos[i][1]) / (pontos[i + 1][0] - pontos[i][0]));
  }
  const tangentes = pontos.map((_, i) => {
    if (i === 0) return inclinacoes[0];
    if (i === n - 1) return inclinacoes[n - 2];
    const [a, b] = [inclinacoes[i - 1], inclinacoes[i]];
    return a * b <= 0 ? 0 : (2 * a * b) / (a + b);  // média harmônica: não ultrapassa os vizinhos
  });
  let d = `M${pontos[0][0]},${pontos[0][1]}`;
  for (let i = 0; i < n - 1; i++) {
    const h = (pontos[i + 1][0] - pontos[i][0]) / 3;
    d += ` C${pontos[i][0] + h},${pontos[i][1] + tangentes[i] * h} ${pontos[i + 1][0] - h},${pontos[i + 1][1] - tangentes[i + 1] * h} ${pontos[i + 1][0]},${pontos[i + 1][1]}`;
  }
  return d;
}

function marcas(min, max, quantidade = 4) {
  const passoBruto = (max - min) / quantidade || 1;
  const potencia = 10 ** Math.floor(Math.log10(passoBruto));
  const passo = [1, 2, 2.5, 5, 10].map((m) => m * potencia).find((p) => p >= passoBruto);
  const inicio = Math.floor(min / passo) * passo;
  const fim = Math.ceil(max / passo) * passo;  // o último tick sempre cobre o máximo
  const lista = [];
  for (let v = inicio; v <= fim + passo * 0.001; v += passo) lista.push(v);
  return lista;
}

export default function GraficoPatrimonio({ serie, capital }) {
  const caixa = useRef(null);
  const [largura, setLargura] = useState(800);
  const [foco, setFoco] = useState(null);

  useEffect(() => {
    const observador = new ResizeObserver(([e]) => setLargura(Math.max(320, e.contentRect.width)));
    observador.observe(caixa.current);
    return () => observador.disconnect();
  }, []);

  const valores = serie.flatMap((p) => SERIES.map((s) => p[s.chave])).filter((v) => v != null);
  const bruto = [Math.min(capital, ...valores), Math.max(capital, ...valores)];
  const folga = (bruto[1] - bruto[0]) * 0.1 || capital * 0.01;
  const ticks = marcas(bruto[0] - folga, bruto[1] + folga);
  const [yMin, yMax] = [ticks[0], ticks[ticks.length - 1]];

  const larguraUtil = largura - MARGEM.esquerda - MARGEM.direita;
  const alturaUtil = ALTURA - MARGEM.topo - MARGEM.base;
  const x = (i) => MARGEM.esquerda + (serie.length > 1 ? (i / (serie.length - 1)) * larguraUtil : larguraUtil / 2);
  const y = (v) => MARGEM.topo + (1 - (v - yMin) / (yMax - yMin)) * alturaUtil;

  // Rótulos no fim das linhas, afastados para não se sobreporem.
  const ultimo = serie[serie.length - 1];
  const rotulos = SERIES.filter((s) => ultimo[s.chave] != null)
    .map((s) => ({ ...s, valor: ultimo[s.chave], yAlvo: y(ultimo[s.chave]) }))
    .sort((a, b) => a.yAlvo - b.yAlvo);
  rotulos.forEach((r, i) => { r.yTexto = i ? Math.max(r.yAlvo, rotulos[i - 1].yTexto + 30) : r.yAlvo; });

  const passoX = Math.max(1, Math.ceil(serie.length / Math.max(2, Math.floor(larguraUtil / 90))));

  function aoMover(evento) {
    const retangulo = evento.currentTarget.getBoundingClientRect();
    const posicao = ((evento.clientX - retangulo.left) / retangulo.width) * largura;
    const indice = serie.length > 1
      ? Math.round(((posicao - MARGEM.esquerda) / larguraUtil) * (serie.length - 1)) : 0;
    setFoco(Math.min(serie.length - 1, Math.max(0, indice)));
  }

  const pontoFoco = foco !== null ? serie[foco] : null;

  return (
    <div className="grafico" ref={caixa}>
      <svg width={largura} height={ALTURA} role="img"
        aria-label="Patrimônio da estratégia, do baseline 1 e do Ibovespa ao longo do tempo">
        {ticks.map((t) => (
          <g key={t}>
            <line className="grafico-grade" x1={MARGEM.esquerda} x2={largura - MARGEM.direita} y1={y(t)} y2={y(t)} />
            <text className="grafico-eixo" x={MARGEM.esquerda - 8} y={y(t)} dy="0.32em" textAnchor="end">{reais(t)}</text>
          </g>
        ))}
        <line className="grafico-referencia" x1={MARGEM.esquerda} x2={largura - MARGEM.direita} y1={y(capital)} y2={y(capital)} />
        {serie.map((p, i) => (i % passoX === 0 || i === serie.length - 1) && (
          <text key={p.data} className="grafico-eixo" x={x(i)} y={ALTURA - 8} textAnchor="middle">
            {formatarData(p.data + "T12:00:00-03:00", false).slice(0, 5)}
          </text>
        ))}

        <defs>
          <linearGradient id="area-estrategia" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--serie-1)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--serie-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* A estratégia é desenhada por último, por cima das referências, com área em degradê. */}
        {[...SERIES].reverse().map((s) => {
          const pontos = serie.map((p, i) => (p[s.chave] == null ? null : [x(i), y(p[s.chave])])).filter(Boolean);
          if (pontos.length === 1) return <circle key={s.chave} cx={pontos[0][0]} cy={pontos[0][1]} r="4" fill={s.cor} />;
          if (pontos.length < 2) return null;
          const linha = caminhoSuave(pontos);
          return (
            <g key={s.chave}>
              {s.chave === "estrategia" && (
                <path d={`${linha} L${pontos[pontos.length - 1][0]},${ALTURA - MARGEM.base} L${pontos[0][0]},${ALTURA - MARGEM.base} Z`}
                  fill="url(#area-estrategia)" />
              )}
              <path d={linha} fill="none" stroke={s.cor} strokeWidth={s.chave === "estrategia" ? 2.5 : 2}
                strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}

        {rotulos.map((r) => (
          <g key={r.chave}>
            <line x1={largura - MARGEM.direita + 6} x2={largura - MARGEM.direita + 18} y1={r.yTexto} y2={r.yTexto} stroke={r.cor} strokeWidth="2" />
            <text className="grafico-rotulo" x={largura - MARGEM.direita + 24} y={r.yTexto} dy="-0.15em">{r.nome.split(" (")[0]}</text>
            <text className="grafico-rotulo-valor" x={largura - MARGEM.direita + 24} y={r.yTexto} dy="1.05em">{reais(r.valor)}</text>
          </g>
        ))}

        {pontoFoco && (
          <g pointerEvents="none">
            <line className="grafico-cursor" x1={x(foco)} x2={x(foco)} y1={MARGEM.topo} y2={ALTURA - MARGEM.base} />
            {SERIES.map((s) => pontoFoco[s.chave] != null && (
              <circle key={s.chave} cx={x(foco)} cy={y(pontoFoco[s.chave])} r="4" fill={s.cor} stroke="var(--painel)" strokeWidth="2" />
            ))}
          </g>
        )}
        <rect x={MARGEM.esquerda} y={MARGEM.topo} width={larguraUtil} height={alturaUtil} fill="transparent"
          onPointerMove={aoMover} onPointerLeave={() => setFoco(null)} />
      </svg>

      {pontoFoco && (
        <div className="grafico-dica" style={{ left: Math.min(x(foco) + 12, largura - 230), top: MARGEM.topo }}>
          <div className="grafico-dica-data">{formatarData(pontoFoco.data + "T12:00:00-03:00", false)}</div>
          {SERIES.map((s) => (
            <div key={s.chave} className="grafico-dica-linha">
              <span className="grafico-amostra" style={{ background: s.cor }} />
              <span>{s.nome.split(" (")[0]}</span>
              <strong>{reais(pontoFoco[s.chave])}</strong>
            </div>
          ))}
        </div>
      )}

      <div className="legenda">
        {SERIES.map((s) => (
          <span key={s.chave}><span className="grafico-amostra" style={{ background: s.cor }} />{s.nome}</span>
        ))}
        <span><span className="grafico-amostra tracejada" />Capital inicial</span>
      </div>
    </div>
  );
}
