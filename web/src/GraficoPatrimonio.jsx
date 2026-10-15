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

        {/* A estratégia é desenhada por último, por cima das referências. */}
        {[...SERIES].reverse().map((s) => {
          const pontos = serie.map((p, i) => (p[s.chave] == null ? null : `${x(i)},${y(p[s.chave])}`)).filter(Boolean);
          return pontos.length > 1
            ? <polyline key={s.chave} points={pontos.join(" ")} fill="none" stroke={s.cor} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            : pontos.length === 1 && <circle key={s.chave} cx={pontos[0].split(",")[0]} cy={pontos[0].split(",")[1]} r="4" fill={s.cor} />;
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
