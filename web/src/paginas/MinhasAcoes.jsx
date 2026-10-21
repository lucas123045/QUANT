import { useMemo, useRef, useState } from "react";
import { formatarData, formatarNumero, formatarPreco, plural, useApi } from "../api.js";
import { Cartao, Secao, dia, pct, tom } from "../comum.jsx";
import { reais } from "../GraficoPatrimonio.jsx";
import { Minigrafico, corTicker } from "../graficos.jsx";
import Icone from "../icones.jsx";
import { Criterios, Estado, Etiqueta } from "../ui.jsx";

/*
 * Minhas ações: as ações que a pessoa JÁ TEM, de verdade, cruzadas com o que o
 * QUANT sabe de cada uma. Os dados ficam só neste navegador (localStorage): são
 * pessoais e nunca vão para o servidor, para o GitHub nem para o site público.
 * Mesmos limites da camada prática: 20% por ação, 30% por setor; IR de ações em
 * operações comuns (15% do lucro se as vendas do mês passarem de R$ 20 mil).
 */
const CHAVE = "quant.minhas_acoes";
const LIMITE_ACAO = 0.20;
const LIMITE_SETOR = 0.30;
const ISENCAO_IR = 20_000;
const ALIQUOTA_IR = 0.15;
const CUSTO_VENDA = 0.00032;  // B3, leilão de fechamento (config.PRATICA_EMOLUMENTOS)

function lerLotes() {
  try {
    const dados = JSON.parse(localStorage.getItem(CHAVE) || "[]");
    return Array.isArray(dados) ? dados.filter(valido) : [];
  } catch {
    return [];
  }
}

function gravarLotes(lotes) {
  try { localStorage.setItem(CHAVE, JSON.stringify(lotes)); return true; } catch { return false; }
}

function valido(l) {
  return l && typeof l.ticker === "string" && Number(l.quantidade) > 0 && Number(l.preco_medio) > 0;
}

/** Junta os lotes de cada ação (preço médio ponderado) e cruza com os preços do QUANT. */
function consolidar(lotes, ativos) {
  const porTicker = new Map();
  for (const l of lotes) {
    const atual = porTicker.get(l.ticker) || { ticker: l.ticker, quantidade: 0, custo: 0, lotes: [] };
    atual.quantidade += Number(l.quantidade);
    atual.custo += Number(l.quantidade) * Number(l.preco_medio);
    atual.lotes.push(l);
    porTicker.set(l.ticker, atual);
  }
  const mapa = Object.fromEntries((ativos || []).map((a) => [a.ticker, a]));
  const posicoes = [...porTicker.values()].map((p) => {
    const a = mapa[p.ticker];
    const preco = a?.preco ?? null;
    const valor = preco != null ? p.quantidade * preco : null;
    return { ...p, ativo: a, preco, valor, preco_medio: p.custo / p.quantidade,
             resultado: valor != null ? valor - p.custo : null,
             variacao_dia: a?.variacao_dia ?? null };
  });
  const total = posicoes.reduce((s, p) => s + (p.valor ?? 0), 0);
  const custo = posicoes.reduce((s, p) => s + p.custo, 0);
  for (const p of posicoes) p.peso = total ? (p.valor ?? 0) / total : 0;
  const setores = {};
  for (const p of posicoes) {
    const setor = p.ativo?.setor || "Outros";
    setores[setor] = (setores[setor] || 0) + p.peso;
  }
  const dia = posicoes.reduce((s, p) => s + (p.valor != null && p.variacao_dia != null
    ? p.valor - p.valor / (1 + p.variacao_dia) : 0), 0);
  return { posicoes: posicoes.sort((a, b) => (b.valor ?? 0) - (a.valor ?? 0)), total, custo, setores, dia };
}

/**
 * Quanto R$ 1 aplicado no CDI no dia `desde` vale no dia `ate` (fator do /api/cdi).
 * A taxa de cada dia remunera até o dia seguinte: vale o fator do último dia ANTES de cada data.
 */
function crescimentoCdi(cdi, desde, ate) {
  if (!cdi?.datas?.length || !desde || desde < cdi.inicio || !ate || ate <= desde) return null;
  const antes = (data) => {
    let lo = 0, hi = cdi.datas.length - 1, achado = -1;
    while (lo <= hi) {
      const meio = (lo + hi) >> 1;
      if (cdi.datas[meio] < data) { achado = meio; lo = meio + 1; } else { hi = meio - 1; }
    }
    return achado >= 0 ? cdi.fator[achado] : 1;
  };
  return antes(ate) / antes(desde);
}

/** O que os lotes com data de compra valeriam se o dinheiro tivesse ido para o CDI. */
function noCdi(lotes, cdi, ate, precoAtual) {
  let custo = 0, cdiValor = 0, hoje = 0, semData = 0;
  for (const l of lotes) {
    const fator = crescimentoCdi(cdi, l.data_compra, ate);
    if (fator == null || precoAtual == null) { semData += 1; continue; }
    const pago = Number(l.quantidade) * Number(l.preco_medio);
    custo += pago;
    cdiValor += pago * fator;
    hoje += Number(l.quantidade) * precoAtual;
  }
  return { custo, cdiValor, hoje, semData, comparados: lotes.length - semData };
}

/** A carteira inteira contra o CDI (soma das ações, cada uma com o seu preço atual). */
function carteiraNoCdi(posicoes, cdi, ate) {
  const total = { custo: 0, cdiValor: 0, hoje: 0, semData: 0, comparados: 0 };
  for (const p of posicoes) {
    const r = noCdi(p.lotes, cdi, ate, p.preco);
    for (const k of Object.keys(total)) total[k] += r[k];
  }
  return total;
}

/** IR estimado se vender tudo hoje (sem vendas anteriores no mês nem prejuízo acumulado). */
function impostoSeVender(posicoes) {
  const vendas = posicoes.reduce((s, p) => s + (p.valor ?? 0), 0);
  const lucro = posicoes.reduce((s, p) => s + (p.valor != null ? p.valor * (1 - CUSTO_VENDA) - p.custo : 0), 0);
  const isento = vendas <= ISENCAO_IR;
  return { vendas, lucro, isento, imposto: isento ? 0 : ALIQUOTA_IR * Math.max(0, lucro) };
}

function Formulario({ ativos, aoAdicionar }) {
  const [ticker, setTicker] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [preco, setPreco] = useState("");
  const [data, setData] = useState("");
  const [erro, setErro] = useState(null);
  const escolhido = ativos.find((a) => a.ticker === ticker);

  function enviar(e) {
    e.preventDefault();
    const q = Number(quantidade);
    const pm = Number(String(preco).replace(",", "."));
    if (!ticker) return setErro("Escolha a ação.");
    if (!Number.isInteger(q) || q <= 0) return setErro("A quantidade é um número inteiro de ações, maior que zero.");
    if (!(pm > 0)) return setErro("Informe o preço médio que você pagou por ação.");
    setErro(null);
    aoAdicionar({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, ticker, quantidade: q, preco_medio: pm,
                  data_compra: data || null });
    setQuantidade(""); setPreco(""); setData("");
  }

  return (
    <form className="minhas-form" onSubmit={enviar}>
      <label>
        <span>Ação</span>
        <select value={ticker} onChange={(e) => setTicker(e.target.value)}>
          <option value="">Escolha…</option>
          {ativos.map((a) => <option key={a.ticker} value={a.ticker}>{a.ticker} · {a.empresa}</option>)}
        </select>
      </label>
      <label>
        <span>Quantidade</span>
        <input type="number" min="1" step="1" inputMode="numeric" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="100" />
      </label>
      <label>
        <span>Preço médio (R$)</span>
        <input type="text" inputMode="decimal" value={preco} onChange={(e) => setPreco(e.target.value)}
          placeholder={escolhido?.preco ? formatarPreco(escolhido.preco) : "0,00"} />
      </label>
      <label>
        <span>Data da compra <small>(opcional)</small></span>
        <input type="date" value={data} onChange={(e) => setData(e.target.value)} />
      </label>
      <button className="botao primario" type="submit">Adicionar</button>
      {erro && <p className="minhas-erro">{erro}</p>}
    </form>
  );
}

/** O que o QUANT viu da ação: a última análise e, se houver, o alerta. */
function Sinal({ u }) {
  if (!u) return <span className="sutil">Nenhuma notícia analisada ainda.</span>;
  const tomDecisao = u.decisao === "compra" ? "positivo" : u.decisao === "venda" ? "negativo" : "neutro";
  return (
    <span className="minhas-sinal">
      <Etiqueta tom={tomDecisao}>{u.decisao === "manter" ? "sem sinal" : u.decisao}</Etiqueta>
      <span>{u.resumo}</span>
    </span>
  );
}

function ComparacaoCdi({ c, indisponivel }) {
  if (indisponivel) return <p className="sutil">O CDI está indisponível agora (Banco Central sem resposta); a comparação volta sozinha.</p>;
  if (!c.comparados) return <p className="sutil">Informe a data da compra para comparar com o CDI.</p>;
  const diferenca = c.hoje - c.cdiValor;
  return (
    <p className={`minhas-cdi ${tom(diferenca)}`}>
      No CDI desde a compra, {reais(c.custo, 2)} seriam hoje {reais(c.cdiValor, 2)}: você está{" "}
      <strong>{reais(Math.abs(diferenca), 2)} {diferenca >= 0 ? "acima" : "abaixo"}</strong> da renda fixa.
      {c.semData > 0 && <span className="sutil"> ({plural(c.semData, "lote sem data ficou", "lotes sem data ficaram")} de fora.)</span>}
    </p>
  );
}

function Posicao({ p, aoRemover, cdi, ate, cdiIndisponivel }) {
  const [aberto, setAberto] = useState(false);
  const u = p.ativo?.ultima_decisao;
  return (
    <li className="expansivel">
      <button className="f-lista-linha" onClick={() => setAberto(!aberto)} aria-expanded={aberto}>
        <span className="f-ativo-logo pequeno" style={{ background: corTicker(p.ticker) }}>{p.ticker.slice(0, 2)}</span>
        <div>
          <strong>{p.ticker} <span className="sutil">· {p.ativo?.empresa}</span></strong>
          <small>
            {formatarNumero(p.quantidade, 0)} ações · preço médio R$ {formatarPreco(p.preco_medio)}
            {p.preco != null ? ` · hoje R$ ${formatarPreco(p.preco)}` : " · sem preço"} · {pct(p.peso, false, 1)} da carteira
          </small>
        </div>
        <div className="minhas-valores">
          <strong>{p.valor != null ? reais(p.valor, 2) : "—"}</strong>
          <small className={tom(p.resultado)}>{p.resultado != null ? `${p.resultado >= 0 ? "+" : "−"}${reais(Math.abs(p.resultado), 2)} (${pct(p.resultado / p.custo)})` : ""}</small>
        </div>
        <span className="seta">{aberto ? "▾" : "▸"}</span>
      </button>
      {aberto && (
        <div className="porque">
          <div className="minhas-detalhe">
            {p.ativo?.minigrafico?.length > 1 && <Minigrafico pontos={p.ativo.minigrafico} largura={180} altura={46} />}
            <dl className="f-numeros">
              <div><dt>No dia</dt><dd className={tom(p.variacao_dia)}>{pct(p.variacao_dia)}</dd></div>
              <div><dt>Em 30 dias</dt><dd className={tom(p.ativo?.variacao_30d)}>{pct(p.ativo?.variacao_30d)}</dd></div>
            </dl>
          </div>
          <div>
            <h4>O que o QUANT viu desta empresa</h4>
            {u ? (
              <>
                <p><Sinal u={u} /></p>
                <small className="sutil">
                  {u.fonte} · {formatarData(u.publicado)} · {u.motivo}
                  {u.url && <> · <a href={u.url} target="_blank" rel="noreferrer">ler</a></>}
                </small>
                {!!u.criterios?.length && <Criterios criterios={u.criterios} />}
              </>
            ) : <p className="sutil">Nenhuma notícia desta empresa analisada ainda.</p>}
          </div>
          <div>
            <h4>Contra a renda fixa</h4>
            <ComparacaoCdi c={noCdi(p.lotes, cdi, ate, p.preco)} indisponivel={cdiIndisponivel} />
          </div>
          <div>
            <h4>Seus lotes</h4>
            <ul className="minhas-lotes">
              {p.lotes.map((l) => (
                <li key={l.id}>
                  {formatarNumero(l.quantidade, 0)} a R$ {formatarPreco(l.preco_medio)}{l.data_compra ? ` em ${dia(l.data_compra)}` : ""}
                  <button className="botao-link" onClick={() => aoRemover(l.id)}>remover</button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </li>
  );
}

function Alertas({ posicoes, setores }) {
  const itens = [];
  for (const p of posicoes) {
    const u = p.ativo?.ultima_decisao;
    if (u?.decisao === "venda") {
      itens.push(["negativo", `${p.ticker}: a regra do QUANT viu um fato negativo, confirmado e relevante (${u.resumo}). Vale olhar com atenção.`]);
    } else if (u?.decisao === "compra") {
      itens.push(["positivo", `${p.ticker}: a regra do QUANT viu um fato positivo, confirmado e relevante (${u.resumo}).`]);
    }
  }
  const lista = (partes) => (partes.length > 1 ? `${partes.slice(0, -1).join(", ")} e ${partes.at(-1)}` : partes[0]);
  const grandes = posicoes.filter((p) => p.peso > LIMITE_ACAO).map((p) => `${p.ticker} (${pct(p.peso, false, 0)})`);
  if (grandes.length) {
    itens.push(["alerta", `${lista(grandes)} ${grandes.length > 1 ? "passam" : "passa"} dos ${Math.round(LIMITE_ACAO * 100)}% da carteira que o QUANT usa como teto por ação: uma notícia ruim pesa muito no total.`]);
  }
  const setoresGrandes = Object.entries(setores).filter(([, peso]) => peso > LIMITE_SETOR && Object.keys(setores).length > 1)
    .map(([setor, peso]) => `${setor} (${pct(peso, false, 0)})`);
  if (setoresGrandes.length) {
    itens.push(["alerta", `${lista(setoresGrandes)} ${setoresGrandes.length > 1 ? "passam" : "passa"} dos ${Math.round(LIMITE_SETOR * 100)}% por setor: ações do mesmo setor costumam cair juntas.`]);
  }
  if (!itens.length) return null;
  return (
    <div className="pilha minhas-alertas">
      {itens.map(([t, texto], i) => <div key={i} className={`aviso tom-${t}`}>{texto}</div>)}
    </div>
  );
}

function Setores({ setores }) {
  const lista = Object.entries(setores).sort((a, b) => b[1] - a[1]);
  return (
    <Cartao titulo="Por setor" subtitulo={`O QUANT limita ${Math.round(LIMITE_SETOR * 100)}% por setor na prática`}>
      <ul className="minhas-setores">
        {lista.map(([setor, peso]) => (
          <li key={setor}>
            <span>{setor}</span>
            <span className="minhas-barra"><span className={peso > LIMITE_SETOR ? "acima" : ""} style={{ width: `${Math.min(100, peso * 100)}%` }} /></span>
            <strong>{pct(peso, false, 0)}</strong>
          </li>
        ))}
      </ul>
    </Cartao>
  );
}

function Imposto({ posicoes }) {
  const ir = impostoSeVender(posicoes);
  return (
    <Cartao titulo="Se vender tudo hoje" subtitulo="Estimativa do imposto de renda (operação comum, não day trade)">
      <dl className="f-numeros">
        <div><dt>Valor vendido</dt><dd>{reais(ir.vendas, 2)}</dd></div>
        <div><dt>Lucro líquido</dt><dd className={tom(ir.lucro)}>{reais(ir.lucro, 2)}</dd></div>
        <div className="largo">
          <dt>Imposto estimado</dt>
          <dd>{ir.isento ? `Isento (vendas até ${reais(ISENCAO_IR)} no mês)` : reais(ir.imposto, 2)}</dd>
        </div>
      </dl>
      <p className="f-nota"><Icone nome="info" tamanho={14} />
        <span>Não considera outras vendas no mês nem prejuízos anteriores a compensar. Vender só parte, em meses diferentes, pode manter as vendas abaixo de {reais(ISENCAO_IR)} e o lucro isento. Confirme com um contador.</span>
      </p>
    </Cartao>
  );
}

/** Lista de códigos para os alertas no celular (só os códigos: as posições ficam aqui). */
function AlertasCelular({ posicoes }) {
  const [copiado, setCopiado] = useState(false);
  if (!posicoes.length) return null;
  const linha = `QUANT_ALERTAS_TICKERS=${posicoes.map((p) => p.ticker).join(",")}`;
  function copiar() {
    navigator.clipboard?.writeText(linha).then(() => { setCopiado(true); setTimeout(() => setCopiado(false), 2000); });
  }
  return (
    <Cartao titulo="Alertas no celular só das suas ações" subtitulo="Aviso quando a regra vir um fato relevante numa empresa que você tem">
      <div className="minhas-alerta-linha">
        <code>{linha}</code>
        <button className="botao" onClick={copiar}>{copiado ? "Copiado" : "Copiar"}</button>
      </div>
      <ol className="minhas-passos">
        <li>Instale o app <strong>ntfy</strong> no celular e assine um tópico com nome difícil de adivinhar.</li>
        <li>No GitHub: Settings › Secrets and variables › Actions › <strong>Variables</strong>: crie <code>QUANT_ALERTAS_TICKERS</code> com a lista acima, e em <strong>Secrets</strong> crie <code>QUANT_NTFY_TOPICO</code> com o nome do tópico.</li>
        <li>No seu computador, as mesmas duas linhas no arquivo <code>.env</code>.</li>
      </ol>
      <p className="f-nota">Vão só os códigos das ações, sem quantidade nem valor: suas posições continuam só neste navegador.</p>
    </Cartao>
  );
}

export default function MinhasAcoes() {
  const { dados: d, erro, carregando } = useApi("/api/simulacao?base=real", 5 * 60 * 1000);
  const respostaCdi = useApi("/api/cdi");
  const cdi = respostaCdi.dados;
  const cdiIndisponivel = !!respostaCdi.erro;
  const [lotes, setLotes] = useState(lerLotes);
  const [aviso, setAviso] = useState(null);
  const entrada = useRef(null);
  const ativos = useMemo(() => (d?.ativos || []).slice().sort((a, b) => a.ticker.localeCompare(b.ticker)), [d]);
  const c = useMemo(() => consolidar(lotes, ativos), [lotes, ativos]);
  const ultimoDia = ativos.map((a) => a.minigrafico?.at(-1)?.data).filter(Boolean).sort().at(-1);

  function salvar(novos) {
    setLotes(novos);
    if (!gravarLotes(novos)) setAviso("Este navegador não deixou guardar os dados (modo anônimo?). Exporte para não perder.");
  }

  function exportar() {
    const blob = new Blob([JSON.stringify({ quant_minhas_acoes: 1, lotes }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement("a"), { href: url, download: "minhas-acoes-quant.json" });
    link.click();
    URL.revokeObjectURL(url);
  }

  function importar(arquivo) {
    arquivo.text().then((texto) => {
      const dados = JSON.parse(texto);
      const lista = (Array.isArray(dados) ? dados : dados.lotes || []).filter(valido);
      if (!lista.length) throw new Error("arquivo sem posições válidas");
      salvar(lista);
      setAviso(`${plural(lista.length, "lote importado", "lotes importados")}.`);
    }).catch((e) => setAviso(`Não foi possível importar: ${e.message}.`));
  }

  return (
    <Estado carregando={carregando && !d} erro={erro}>
      <div className="f-pagina">
        <div className="f-aviso">
          <Icone nome="escudo" tamanho={16} />
          <span>
            As ações que você <strong>já tem</strong>, cruzadas com o que o QUANT analisa. Seus dados ficam <strong>só neste
            navegador</strong>: não vão para o servidor nem para o site público. Use "Exportar" para ter uma cópia.
          </span>
        </div>

        {c.posicoes.length > 0 && (
          <div className="f-resumo">
            <section className="f-saldo">
              <div className="f-saldo-topo"><span>Valor das suas ações{ultimoDia ? ` (fechamento ${dia(ultimoDia).slice(0, 5)})` : ""}</span></div>
              <span className="f-saldo-valor">{reais(c.total, 2)}</span>
              <div className="f-saldo-rodape">
                <span className={tom(c.total - c.custo)}>{c.total - c.custo >= 0 ? "+" : "−"}{reais(Math.abs(c.total - c.custo), 2)} ({pct(c.custo ? c.total / c.custo - 1 : 0)}) sobre o que você pagou</span>
              </div>
            </section>
            <section className="f-estat">
              <span className="f-estat-icone"><Icone nome="dinheiro" tamanho={18} /></span>
              <span className="f-estat-valor">{reais(c.custo, 2)}</span>
              <span className="f-estat-rotulo">Quanto você pagou</span>
            </section>
            <section className="f-estat">
              <span className="f-estat-icone"><Icone nome="grafico" tamanho={18} /></span>
              <span className={`f-estat-valor ${tom(c.dia)}`}>{c.dia >= 0 ? "+" : "−"}{reais(Math.abs(c.dia), 2)}</span>
              <span className="f-estat-rotulo">No último pregão</span>
            </section>
            <section className="f-estat">
              <span className="f-estat-icone"><Icone nome="painel" tamanho={18} /></span>
              <span className="f-estat-valor">{c.posicoes.length}</span>
              <span className="f-estat-rotulo">{c.posicoes.length === 1 ? "ação" : "ações diferentes"}</span>
            </section>
          </div>
        )}

        <Alertas posicoes={c.posicoes} setores={c.setores} />

        <Cartao titulo="Adicionar uma ação que você tem" subtitulo="Use o preço médio da sua corretora; vários lotes da mesma ação são somados">
          <Formulario ativos={ativos} aoAdicionar={(l) => salvar([...lotes, l])} />
          <div className="minhas-acoes-botoes">
            <button className="botao" onClick={exportar} disabled={!lotes.length}>Exportar</button>
            <button className="botao" onClick={() => entrada.current?.click()}>Importar</button>
            <input ref={entrada} type="file" accept="application/json,.json" hidden
              onChange={(e) => { if (e.target.files?.[0]) importar(e.target.files[0]); e.target.value = ""; }} />
            {!!lotes.length && (
              <button className="botao-link" onClick={() => { if (window.confirm("Apagar todas as suas ações deste navegador?")) salvar([]); }}>
                Apagar tudo
              </button>
            )}
          </div>
          {aviso && <p className="f-nota">{aviso}</p>}
        </Cartao>

        {c.posicoes.length > 0 ? (
          <>
            <Secao titulo="Suas posições" texto="Toque numa ação para ver o que o QUANT analisou dela." />
            <Cartao>
              <ul className="f-lista">
                {c.posicoes.map((p) => <Posicao key={p.ticker} p={p} cdi={cdi} ate={ultimoDia} cdiIndisponivel={cdiIndisponivel}
                  aoRemover={(id) => salvar(lotes.filter((l) => l.id !== id))} />)}
              </ul>
            </Cartao>
            <div className="f-grade">
              <Setores setores={c.setores} />
              <Imposto posicoes={c.posicoes} />
              <Cartao titulo="Contra a renda fixa" subtitulo="O mesmo dinheiro aplicado a 100% do CDI desde cada compra (antes do IR)">
                <ComparacaoCdi c={carteiraNoCdi(c.posicoes, cdi, ultimoDia)} indisponivel={cdiIndisponivel} />
              </Cartao>
            </div>
            <AlertasCelular posicoes={c.posicoes} />
          </>
        ) : (
          <div className="vazio">Nenhuma ação ainda. Adicione as que você tem para o QUANT acompanhar junto.</div>
        )}
        <p className="f-rodape-aviso">Preços de fechamento do último pregão completo. O QUANT acompanha {ativos.length} ações; não é recomendação de investimento.</p>
      </div>
    </Estado>
  );
}
