import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Vitrine: a versão publicada (build de produção, ex.: Vercel) não tem a API
 * Python. Ela lê os arquivos JSON da vitrine:
 * 1. ao vivo, do ramo "dados" do GitHub (VITE_DADOS_URL), atualizado pela coleta
 *    automática na nuvem a cada 30 minutos — o site não precisa ser republicado;
 * 2. se esse endereço falhar, dos arquivos publicados junto com o site (/dados/).
 * Em desenvolvimento (`npm run dev`), tudo vem da API ao vivo.
 */
export const VITRINE = import.meta.env.PROD && import.meta.env.VITE_USAR_API !== "1";
const DADOS_AO_VIVO = (import.meta.env.VITE_DADOS_URL || "").replace(/\/$/, "");

export const MENSAGEM_VITRINE =
  "Na versão online, a coleta e a análise rodam na nuvem: use a página \"Rodar agora\".";

const cacheVitrine = new Map();

async function buscarJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status === 404 ? "Dados ainda não publicados." : `Erro ${r.status}`);
  return r.json();
}

/**
 * Site online: estado da nuvem pela função do Vercel (api/nuvem.js) — execuções
 * recentes no GitHub e o commit mais novo do ramo "dados".
 */
export function estadoNuvem() {
  return buscar("/api/nuvem", {});
}

/** Pede ao GitHub para rodar agora ("pipeline" ou "coleta"). */
export function rodarNaNuvem(senha, tarefa) {
  return buscar("/api/nuvem", { method: "POST", body: JSON.stringify({ senha, tarefa }) });
}

// Lê a vitrine pelo endereço do commit (imutável): uma coleta que acabou de
// terminar aparece na hora, sem esperar os ~5 min de cache do endereço do ramo.
let enderecoAoVivo = null;
function baseAoVivo() {
  if (!enderecoAoVivo) {
    enderecoAoVivo = estadoNuvem()
      .then((e) => (e?.dados_sha ? DADOS_AO_VIVO.replace("/dados/", `/${e.dados_sha}/`) : DADOS_AO_VIVO))
      .catch(() => DADOS_AO_VIVO);
  }
  return enderecoAoVivo;
}

/** Arquivo da vitrine: primeiro o ao vivo (ramo "dados"), depois o publicado com o site. */
export async function lerArquivo(nome) {
  if (!cacheVitrine.has(nome)) {
    const local = () => buscarJson(`/dados/${nome}`);
    const promessa = DADOS_AO_VIVO
      ? baseAoVivo().then((base) => buscarJson(`${base}/${nome}`)).catch(local)
      : local();
    cacheVitrine.set(nome, promessa);
    promessa.catch(() => cacheVitrine.delete(nome));  // erro não fica guardado
  }
  const dados = await cacheVitrine.get(nome);
  if (dados && dados._erro) throw new Error(dados.detail || `Erro ${dados._erro}`);
  return dados;
}

async function pedirVitrine(caminho, opcoes) {
  if (opcoes.method && opcoes.method !== "GET") throw new Error(MENSAGEM_VITRINE);
  const url = new URL(caminho, window.location.origin);
  const base = url.searchParams.get("base") === "teste" ? "teste" : "real";
  const partes = url.pathname.replace(/^\/api\//, "").split("/");

  switch (partes[0]) {
    case "status": return lerArquivo("status.json");
    case "config": return lerArquivo("config.json");
    case "funil": return lerArquivo(`funil-${base}.json`);
    case "operacoes": return lerArquivo(`operacoes-${base}.json`);
    case "simulacao": return lerArquivo(`simulacao-${base}.json`);
    case "tarefas": return [];
    case "execucoes":
      if (partes[1]) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(partes[1])) throw new Error("data inválida");
        return lerArquivo(`execucoes-${base}/${partes[1]}.json`);
      }
      return lerArquivo(`execucoes-${base}.json`);
    case "noticias": {
      // Mesmos filtros da API, aplicados no navegador.
      const { itens, ultima_coleta: ultimaColeta = null } = await lerArquivo(`noticias-${base}.json`);
      const ticker = url.searchParams.get("ticker");
      const termo = (url.searchParams.get("q") || "").toLowerCase();
      const soCarteira = url.searchParams.get("so_carteira") === "true";
      const filtrados = itens.filter((n) =>
        (!soCarteira || n.tickers_atuais.length)
        && (!ticker || n.tickers_atuais.includes(ticker))
        && (!termo || `${n.titulo} ${n.texto}`.toLowerCase().includes(termo)));
      const limite = Number(url.searchParams.get("limite")) || 300;
      return { total: filtrados.length, itens: filtrados.slice(0, limite), ultima_coleta: ultimaColeta };
    }
    default:
      throw new Error("Recurso indisponível na versão online.");
  }
}

// Leituras iguais em andamento compartilham a mesma resposta (o React, em
// desenvolvimento, monta cada página duas vezes e pediria tudo em dobro).
const leiturasEmAndamento = new Map();

export function pedir(caminho, opcoes = {}) {
  if (VITRINE) return pedirVitrine(caminho, opcoes);
  if (opcoes.method && opcoes.method !== "GET") return buscar(caminho, opcoes);
  if (!leiturasEmAndamento.has(caminho)) {
    leiturasEmAndamento.set(caminho, buscar(caminho, opcoes)
      .finally(() => leiturasEmAndamento.delete(caminho)));
  }
  return leiturasEmAndamento.get(caminho);
}

async function buscar(caminho, opcoes) {
  const resposta = await fetch(caminho, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    throw new Error(corpo?.detail || `Erro ${resposta.status}`);
  }
  return corpo;
}

/**
 * Carrega um endpoint e recarrega quando o caminho muda.
 * `intervaloMs` (opcional): recarrega sozinho de tempos em tempos, só com a aba
 * visível e só com a API ao vivo (na vitrine os dados não mudam).
 */
export function useApi(caminho, intervaloMs = 0) {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [carregando, setCarregando] = useState(true);

  // Só a resposta do pedido mais recente vale: numa busca digitada rápido, uma
  // resposta antiga que chegasse por último substituiria a atual na tela.
  const ultimoPedido = useRef(0);

  const recarregar = useCallback(() => {
    if (!caminho) return;
    const pedido = ++ultimoPedido.current;
    const atual = () => pedido === ultimoPedido.current;
    setCarregando(true);
    pedir(caminho)
      .then((d) => { if (atual()) { setDados(d); setErro(null); } })
      .catch((e) => { if (atual()) setErro(e.message); })
      .finally(() => { if (atual()) setCarregando(false); });
  }, [caminho]);

  useEffect(recarregar, [recarregar]);
  useEffect(() => {
    if (!intervaloMs || VITRINE) return undefined;
    const id = setInterval(() => { if (document.visibilityState === "visible") recarregar(); }, intervaloMs);
    // Voltou para a aba depois de um tempo: atualiza na hora.
    const aoVoltar = () => { if (document.visibilityState === "visible") recarregar(); };
    document.addEventListener("visibilitychange", aoVoltar);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", aoVoltar); };
  }, [intervaloMs, recarregar]);
  return { dados, erro, carregando, recarregar };
}

export function formatarData(iso, comHora = true) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit", month: "2-digit", year: "numeric",
    ...(comHora ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function formatarNumero(valor, casas = 2, minimo = 0) {
  if (valor === null || valor === undefined) return "—";
  if (typeof valor !== "number") return String(valor);
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: minimo, maximumFractionDigits: casas });
}

/** "1 notícia", "3 notícias" — em vez de "notícia(s)". */
export function plural(n, singular, pluralTexto) {
  return `${n.toLocaleString("pt-BR")} ${n === 1 ? singular : pluralTexto}`;
}

export function formatarPreco(valor) {
  return formatarNumero(valor, 2, 2);
}
