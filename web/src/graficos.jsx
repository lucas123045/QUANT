import { useState } from "react";

// Cor fixa por ação (a cor segue a empresa, nunca a posição no ranking).
export const COR_TICKER = {
  PETR4: "var(--cat-1)", VALE3: "var(--cat-2)", ITUB4: "var(--cat-3)",
  BBDC4: "var(--cat-4)", ABEV3: "var(--cat-5)", CAIXA: "var(--cat-caixa)",
};

/** Rosca de alocação. fatias: [{chave, rotulo, valor}] */
export function Rosca({ fatias, tamanho = 168, espessura = 22, centro, formatar }) {
  const [foco, setFoco] = useState(null);
  const total = fatias.reduce((s, f) => s + Math.max(0, f.valor), 0) || 1;
  const raio = (tamanho - espessura) / 2;
  const circ = 2 * Math.PI * raio;
  const folga = fatias.length > 1 ? 2 : 0;  // 2px de fundo entre fatias
  let acumulado = 0;
  const ativa = fatias.find((f) => f.chave === foco);

  return (
    <div className="rosca">
      <svg width={tamanho} height={tamanho} viewBox={`0 0 ${tamanho} ${tamanho}`} role="img"
        aria-label="Alocação do patrimônio">
        <g transform={`rotate(-90 ${tamanho / 2} ${tamanho / 2})`}>
          <circle cx={tamanho / 2} cy={tamanho / 2} r={raio} fill="none" stroke="var(--painel-2)" strokeWidth={espessura} />
          {fatias.map((f) => {
            const comprimento = (Math.max(0, f.valor) / total) * circ;
            const deslocamento = -acumulado;
            acumulado += comprimento;
            return (
              <circle key={f.chave} cx={tamanho / 2} cy={tamanho / 2} r={raio} fill="none"
                stroke={COR_TICKER[f.chave] || "var(--cat-caixa)"}
                strokeWidth={foco === f.chave ? espessura + 4 : espessura}
                strokeDasharray={`${Math.max(0, comprimento - folga)} ${circ}`} strokeDashoffset={deslocamento}
                onPointerEnter={() => setFoco(f.chave)} onPointerLeave={() => setFoco(null)}
                style={{ cursor: "default", transition: "stroke-width .15s" }} />
            );
          })}
        </g>
      </svg>
      <div className="rosca-centro">
        {ativa ? (
          <>
            <span className="rotulo">{ativa.rotulo}</span>
            <strong>{Math.round((ativa.valor / total) * 100)}%</strong>
            <span className="sutil">{formatar(ativa.valor)}</span>
          </>
        ) : centro}
      </div>
    </div>
  );
}

/** Barras horizontais de retorno (comparação entre carteiras). itens: [{chave, rotulo, valor, cor}] */
export function BarrasComparacao({ itens, formatar }) {
  const maximo = Math.max(0.0001, ...itens.map((i) => Math.abs(i.valor)));
  const temNegativo = itens.some((i) => i.valor < 0);
  return (
    <div className="barras-comp">
      {itens.map((i) => {
        const largura = (Math.abs(i.valor) / maximo) * (temNegativo ? 50 : 100);
        return (
          <div key={i.chave} className="barras-comp-linha" title={`${i.rotulo}: ${formatar(i.valor)}`}>
            <span className="barras-comp-rotulo"><span className="grafico-amostra" style={{ background: i.cor }} />{i.rotulo}</span>
            <div className={`barras-comp-trilho ${temNegativo ? "com-zero" : ""}`}>
              <div className="barras-comp-barra" style={{
                width: `${largura}%`, background: i.cor,
                ...(temNegativo ? (i.valor >= 0 ? { left: "50%" } : { right: "50%" }) : { left: 0 }),
              }} />
            </div>
            <span className="barras-comp-valor">{formatar(i.valor)}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Barras divergentes: rendimento de cada decisão, para cima (ganho) ou para baixo (perda). */
export function BarrasRendimento({ itens, formatar }) {
  const [foco, setFoco] = useState(null);
  // Só reserva espaço abaixo da linha do zero se houver perda (e acima, se houver ganho).
  const comGanho = itens.some((i) => i.valor >= 0);
  const comPerda = itens.some((i) => i.valor < 0);
  const metade = 90;
  const altura = comGanho && comPerda ? 2 * metade : metade + 22;
  const meio = comGanho ? metade : 22;
  const maximo = Math.max(0.01, ...itens.map((i) => Math.abs(i.valor)));
  const largura = Math.max(36, Math.min(64, 640 / Math.max(1, itens.length)));
  const escala = (metade - 22) / maximo;
  const total = itens.length * largura;
  return (
    <div className="barras-rend">
      <svg width={Math.max(total, 200)} height={altura} role="img" aria-label="Rendimento de cada decisão">
        <line x1="0" x2={Math.max(total, 200)} y1={meio} y2={meio} className="grafico-referencia" />
        {itens.map((i, n) => {
          const h = Math.max(2, Math.abs(i.valor) * escala);
          const x = n * largura + largura * 0.2;
          const w = largura * 0.6;
          const positivo = i.valor >= 0;
          return (
            <g key={n} onPointerEnter={() => setFoco(n)} onPointerLeave={() => setFoco(null)}>
              <rect x={n * largura} y="0" width={largura} height={altura} fill="transparent" />
              <rect x={x} y={positivo ? meio - h : meio} width={w} height={h} rx="2"
                fill={positivo ? "var(--positivo)" : "var(--negativo)"} opacity={foco === null || foco === n ? 1 : 0.45} />
              <text x={x + w / 2} y={positivo ? meio - h - 6 : meio + h + 13} textAnchor="middle" className="grafico-rotulo-valor">
                {formatar(i.valor)}
              </text>
              <text x={x + w / 2} y={positivo ? meio + 14 : meio - 6} textAnchor="middle" className="grafico-eixo">{i.rotulo}</text>
            </g>
          );
        })}
      </svg>
      {foco !== null && itens[foco].detalhe && <div className="barras-rend-dica">{itens[foco].detalhe}</div>}
    </div>
  );
}

/** Minigráfico de preço (sem eixos). pontos: [{data, preco}] */
export function Minigrafico({ pontos, largura = 140, altura = 40 }) {
  if (!pontos || pontos.length < 2) return <div className="minigrafico vazio-mini">sem histórico</div>;
  const valores = pontos.map((p) => p.preco);
  const [min, max] = [Math.min(...valores), Math.max(...valores)];
  const y = (v) => altura - 4 - ((v - min) / (max - min || 1)) * (altura - 8);
  const x = (n) => (n / (pontos.length - 1)) * (largura - 6) + 3;
  const subiu = valores[valores.length - 1] >= valores[0];
  const cor = subiu ? "var(--positivo)" : "var(--negativo)";
  const linha = pontos.map((p, n) => `${x(n)},${y(p.preco)}`).join(" ");
  return (
    <svg className="minigrafico" width={largura} height={altura} role="img"
      aria-label={`Preço nos últimos ${pontos.length} pregões: ${subiu ? "alta" : "queda"}`}>
      <polygon points={`${x(0)},${altura} ${linha} ${x(pontos.length - 1)},${altura}`} fill={cor} opacity="0.12" />
      <polyline points={linha} fill="none" stroke={cor} strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={x(pontos.length - 1)} cy={y(valores[valores.length - 1])} r="2.5" fill={cor} />
    </svg>
  );
}
