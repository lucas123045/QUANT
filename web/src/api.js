import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Vitrine: a versão publicada (build de produção, ex.: Vercel) não tem a API
 * Python. Ela lê os arquivos gerados por `npm run vitrine` em /dados/.
 * Em desenvolvimento (`npm run dev`), tudo vem da API ao vivo.
 */
export const VITRINE = import.meta.env.PROD && import.meta.env.VITE_USAR_API !== "1";

export const MENSAGEM_VITRINE =
  "Esta é a versão online, somente leitura. Para coletar notícias e rodar a IA, use o sistema no computador (npm run dev).";

const cacheVitrine = new Map();

async function lerArquivo(nome) {
  if (!cacheVitrine.has(nome)) {
    cacheVitrine.set(nome, fetch(`/dados/${nome}`).then(async (r) => {
      if (!r.ok) throw new Error(r.status === 404 ? "Dados ainda não publicados (rode npm run vitrine)." : `Erro ${r.status}`);
      return r.json();
    }));
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
      const { itens } = await lerArquivo(`noticias-${base}.json`);
      const ticker = url.searchParams.get("ticker");
      const termo = (url.searchParams.get("q") || "").toLowerCase();
      const soCarteira = url.searchParams.get("so_carteira") === "true";
      const filtrados = itens.filter((n) =>
        (!soCarteira || n.tickers_atuais.length)
        && (!ticker || n.tickers_atuais.includes(ticker))
        && (!termo || `${n.titulo} ${n.texto}`.toLowerCase().includes(termo)));
      const limite = Number(url.searchParams.get("limite")) || 300;
      return { total: filtrados.length, itens: filtrados.slice(0, limite) };
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

/** Carrega um endpoint e recarrega quando o caminho muda. */
export function useApi(caminho) {
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
