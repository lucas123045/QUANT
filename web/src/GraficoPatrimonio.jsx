import { useEffect, useRef, useState } from "react";
import { formatarData } from "./api.js";

export const SERIES = [
  { chave: "estrategia", nome: "Estratégia (regra)", cor: "var(--serie-1)" },
  { chave: "baseline_1", nome: "Baseline 1 (toda notícia positiva)", cor: "var(--serie-2)" },
  { chave: "ibovespa", nome: "Ibovespa (comprar e segurar)", cor: "var(--serie-3)" },
  { chave: "cdi", nome: "Renda fixa (100% do CDI)", cor: "var(--serie-4)" },
];

const ALTURA = 300;
const MARGEM = { topo: 16, direita: 150, base: 30, esquerda: 78 };
// Celular: sem os rótulos no fim das linhas (a legenda embaixo já nomeia as séries).
const LARGURA_COMPACTA = 560;
const ALTURA_COMPACTA = 230;
const MARGEM_COMPACTA = { topo: 14, direita: 10, base: 28, esquerda: 60 };

const reaisCompacto = (valor) => valor.toLocaleString("pt-BR", {
  style: "currency", currency: "BRL", notation: "compact", minimumFractionDigits: 0, maximumFractionDigits: 1 });

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

/** `series`: quais linhas desenhar ([{chave, nome, cor}]); a primeira ganha a área em degradê. */
export default function GraficoPatrimonio({ serie, capital, series: definicoes = SERIES }) {
  const caixa = useRef(null);
  const [largura, setLargura] = useState(800);
  const [foco, setFoco] = useState(null);

  useEffect(() => {
    const observador = new ResizeObserver(([e]) => setLargura(Math.max(260, e.contentRect.width)));
    observador.observe(caixa.current);
    return () => observador.disconnect();
  }, []);

  const compacto = largura < LARGURA_COMPACTA;
  const M = compacto ? MARGEM_COMPACTA : MARGEM;
  const altura = compacto ? ALTURA_COMPACTA : ALTURA;

  // Só as séries com dados (o CDI some quando o Banco Central não responde).
  const series = definicoes.filter((s) => serie.some((p) => p[s.chave] != null));
  const principal = definicoes[0].chave;
  const valores = serie.flatMap((p) => series.map((s) => p[s.chave])).filter((v) => v != null);
  const bruto = [Math.min(capital, ...valores), Math.max(capital, ...valores)];
  const folga = (bruto[1] - bruto[0]) * 0.1 || capital * 0.01;
  const ticks = marcas(bruto[0] - folga, bruto[1] + folga);
  const [yMin, yMax] = [ticks[0], ticks[ticks.length - 1]];

  const larguraUtil = largura - M.esquerda - M.direita;
  const alturaUtil = altura - M.topo - M.base;
  const x = (i) => M.esquerda + (serie.length > 1 ? (i / (serie.length - 1)) * larguraUtil : larguraUtil / 2);
  const y = (v) => M.topo + (1 - (v - yMin) / (yMax - yMin)) * alturaUtil;

  // Rótulos no fim das linhas, afastados para não se sobreporem.
  const ultimo = serie[serie.length - 1];
  const rotulos = series.filter((s) => ultimo[s.chave] != null)
    .map((s) => ({ ...s, valor: ultimo[s.chave], yAlvo: y(ultimo[s.chave]) }))
    .sort((a, b) => a.yAlvo - b.yAlvo);
  rotulos.forEach((r, i) => { r.yTexto = i ? Math.max(r.yAlvo, rotulos[i - 1].yTexto + 30) : r.yAlvo; });

  const passoX = Math.max(1, Math.ceil(serie.length / Math.max(2, Math.floor(larguraUtil / 90))));
  // Datas do eixo: a cada passoX, mais o último dia; um rótulo regular colado
  // no último sai, para os dois não se sobreporem.
  const ultimoIndice = serie.length - 1;
  const datasEixo = serie.map((_, i) => i).filter((i) => i === ultimoIndice
    || (i % passoX === 0 && (ultimoIndice - i) * (larguraUtil / Math.max(1, ultimoIndice)) >= 64));
  const ancora = (i) => (serie.length < 2 ? "middle" : i === 0 ? "start" : i === ultimoIndice ? "end" : "middle");

  function aoMover(evento) {
    // O retângulo de captura cobre só a área útil: a fração horizontal já é a do eixo X.
    const retangulo = evento.currentTarget.getBoundingClientRect();
    const fracao = (evento.clientX - retangulo.left) / retangulo.width;
    const indice = serie.length > 1 ? Math.round(fracao * (serie.length - 1)) : 0;
    setFoco(Math.min(serie.length - 1, Math.max(0, indice)));
  }

  const pontoFoco = foco !== null ? serie[foco] : null;

  return (
    <div className="grafico" ref={caixa}>
      <svg width={largura} height={altura} role="img"
        aria-label="Patrimônio da estratégia e das alternativas de comparação ao longo do tempo">
        {ticks.map((t) => (
          <g key={t}>
            <line className="grafico-grade" x1={M.esquerda} x2={largura - M.direita} y1={y(t)} y2={y(t)} />
            <text className="grafico-eixo" x={M.esquerda - 8} y={y(t)} dy="0.32em" textAnchor="end">{compacto ? reaisCompacto(t) : reais(t)}</text>
          </g>
        ))}
        <line className="grafico-referencia" x1={M.esquerda} x2={largura - M.direita} y1={y(capital)} y2={y(capital)} />
        {datasEixo.map((i) => (
          <text key={serie[i].data} className="grafico-eixo" x={x(i)} y={altura - 8} textAnchor={ancora(i)}>
            {formatarData(serie[i].data + "T12:00:00-03:00", false).slice(0, 5)}
          </text>
        ))}

        <defs>
          <linearGradient id="area-estrategia" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--serie-1)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--serie-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* A série principal é desenhada por último, por cima das referências, com área em degradê. */}
        {[...series].reverse().map((s, ordem) => {
          const pontos = serie.map((p, i) => (p[s.chave] == null ? null : [x(i), y(p[s.chave])])).filter(Boolean);
          if (pontos.length === 1) return <circle key={s.chave} cx={pontos[0][0]} cy={pontos[0][1]} r="4" fill={s.cor} />;
          if (pontos.length < 2) return null;
          const linha = caminhoSuave(pontos);
          return (
            <g key={s.chave}>
              {s.chave === principal && (
                <path d={`${linha} L${pontos[pontos.length - 1][0]},${altura - M.base} L${pontos[0][0]},${altura - M.base} Z`}
                  fill="url(#area-estrategia)" className="area-surge" />
              )}
              <path d={linha} fill="none" stroke={s.cor} strokeWidth={s.chave === principal ? 2.5 : 2}
                pathLength="1" className="linha-desenha" style={{ animationDelay: `${ordem * 120}ms` }}
                strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}

        {!compacto && rotulos.map((r) => (
          <g key={r.chave}>
            <line x1={largura - M.direita + 6} x2={largura - M.direita + 18} y1={r.yTexto} y2={r.yTexto} stroke={r.cor} strokeWidth="2" />
            <text className="grafico-rotulo" x={largura - M.direita + 24} y={r.yTexto} dy="-0.15em">{r.nome.split(" (")[0]}</text>
            <text className="grafico-rotulo-valor" x={largura - M.direita + 24} y={r.yTexto} dy="1.05em">{reais(r.valor)}</text>
          </g>
        ))}

        {pontoFoco && (
          <g pointerEvents="none">
            <line className="grafico-cursor" x1={x(foco)} x2={x(foco)} y1={M.topo} y2={altura - M.base} />
            {series.map((s) => pontoFoco[s.chave] != null && (
              <circle key={s.chave} cx={x(foco)} cy={y(pontoFoco[s.chave])} r="4" fill={s.cor} stroke="var(--painel)" strokeWidth="2" />
            ))}
          </g>
        )}
        <rect x={M.esquerda} y={M.topo} width={larguraUtil} height={alturaUtil} fill="transparent"
          onPointerMove={aoMover} onPointerDown={aoMover}
          /* No toque, o "saiu" dispara assim que o dedo levanta: só o mouse esconde a dica. */
          onPointerLeave={(e) => { if (e.pointerType === "mouse") setFoco(null); }} />
      </svg>

      {pontoFoco && (
        <div className="grafico-dica" style={{ left: Math.max(0, Math.min(x(foco) + 12, largura - (compacto ? 200 : 230))), top: M.topo }}>
          <div className="grafico-dica-data">{formatarData(pontoFoco.data + "T12:00:00-03:00", false)}</div>
          {series.map((s) => (
            <div key={s.chave} className="grafico-dica-linha">
              <span className="grafico-amostra" style={{ background: s.cor }} />
              <span>{s.nome.split(" (")[0]}</span>
              <strong>{reais(pontoFoco[s.chave])}</strong>
            </div>
          ))}
        </div>
      )}

      <div className="legenda">
        {series.map((s) => (
          <span key={s.chave}><span className="grafico-amostra" style={{ background: s.cor }} />{s.nome}</span>
        ))}
        <span><span className="grafico-amostra tracejada" />Capital inicial</span>
      </div>
    </div>
  );
}
