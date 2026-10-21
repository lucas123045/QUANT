// Função do Vercel (/api/nuvem): o botão "Rodar agora" do site online.
//
// O QUANT não roda dentro do Vercel: lá não há disco que dure (o arquivo de
// notícias e o log de decisões se perderiam a cada chamada) e cada função tem
// poucos minutos de vida. Quem roda é o GitHub Actions (.github/workflows/quant.yml),
// que guarda tudo no ramo "dados". Esta função só:
//   GET  -> as últimas execuções na nuvem e o commit mais recente do ramo "dados";
//   GET  ?agendar=<QUANT_CRON_SEGREDO> -> dispara o pipeline (para um agendador externo);
//   POST -> {senha, tarefa} confere a senha e manda o GitHub rodar agora.
//
// Por que um agendador externo: o "schedule" do GitHub Actions atrasa ou pula
// execuções quando os servidores estão ocupados (em 21/10/2026, o "a cada 30
// minutos" rodou 2 vezes em 9 horas). Um serviço como o cron-job.org chamando
// esta URL a cada 30 minutos mantém a coleta em dia.
//
// Variáveis de ambiente (Vercel > Settings > Environment Variables):
//   QUANT_SENHA         senha para rodar (sem ela, o botão fica desligado)
//   QUANT_GITHUB_TOKEN  token do GitHub com permissão "Actions: Read and write" no repositório
//   QUANT_REPOSITORIO   opcional; padrão lucas123045/QUANT
//   QUANT_CRON_SEGREDO  opcional; segredo longo do agendador externo (diferente da senha)
// A chave da OpenAI NÃO fica aqui: ela é o segredo LLM_API_KEY do GitHub.
import { timingSafeEqual, createHash } from "node:crypto";

const REPOSITORIO = process.env.QUANT_REPOSITORIO || "lucas123045/QUANT";
const WORKFLOW = "quant.yml";
const TAREFAS = new Set(["pipeline", "coleta"]);

function github(caminho, opcoes = {}) {
  const token = process.env.QUANT_GITHUB_TOKEN;
  return fetch(`https://api.github.com/repos/${REPOSITORIO}${caminho}`, {
    ...opcoes,
    headers: {
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "quant-academico",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opcoes.headers,
    },
  });
}

// Compara pelo hash: mesmo tamanho sempre, e sem vazar a senha pelo tempo de resposta.
function confere(recebida, certa) {
  if (!certa || typeof recebida !== "string") return false;
  const h = (t) => createHash("sha256").update(t).digest();
  return timingSafeEqual(h(recebida), h(certa));
}

function senhaConfere(recebida) {
  return confere(recebida, process.env.QUANT_SENHA);
}

function disparar(tarefa) {
  return github(`/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: { tarefa } }),
  });
}

/** Disparo do agendador externo: um pipeline por vez, nunca empilhado. */
async function agendado(res, segredo) {
  if (!process.env.QUANT_GITHUB_TOKEN || !confere(segredo, process.env.QUANT_CRON_SEGREDO)) {
    await new Promise((r) => setTimeout(r, 1000));
    return res.status(401).json({ detail: "Segredo do agendador incorreto ou não configurado." });
  }
  const { execucoes } = await estado();
  if (execucoes.some((e) => e.status !== "completed")) {
    return res.status(200).json({ ok: true, disparado: false, motivo: "já há uma execução na fila ou rodando" });
  }
  const r = await disparar("pipeline");
  if (!r.ok) return res.status(502).json({ detail: `O GitHub recusou o pedido (${r.status}).` });
  return res.status(202).json({ ok: true, disparado: true });
}

async function estado() {
  const [execucoes, ramo] = await Promise.all([
    github(`/actions/workflows/${WORKFLOW}/runs?per_page=8`),
    github("/commits/dados"),
  ]);
  const lista = execucoes.ok ? (await execucoes.json()).workflow_runs : [];
  return {
    configurado: Boolean(process.env.QUANT_SENHA && process.env.QUANT_GITHUB_TOKEN),
    dados_sha: ramo.ok ? (await ramo.json()).sha : null,
    execucoes: lista.map((r) => ({
      id: r.id, titulo: r.display_title, evento: r.event, status: r.status,
      conclusao: r.conclusion, inicio: r.run_started_at || r.created_at, fim: r.updated_at, url: r.html_url,
    })),
  };
}

export default async function handler(req, res) {
  try {
    if (req.method === "GET" && req.query?.agendar !== undefined) {
      res.setHeader("Cache-Control", "no-store");
      return await agendado(res, String(req.query.agendar));
    }
    if (req.method === "GET") {
      res.setHeader("Cache-Control", "public, s-maxage=5, stale-while-revalidate=10");
      return res.status(200).json(await estado());
    }
    if (req.method !== "POST") return res.status(405).json({ detail: "Método não permitido." });

    const { senha, tarefa = "pipeline" } = req.body || {};
    if (!process.env.QUANT_SENHA || !process.env.QUANT_GITHUB_TOKEN) {
      return res.status(503).json({ detail: "O botão ainda não foi configurado no Vercel (QUANT_SENHA e QUANT_GITHUB_TOKEN)." });
    }
    if (!senhaConfere(senha)) {
      await new Promise((r) => setTimeout(r, 1000));  // freia quem tenta adivinhar
      return res.status(401).json({ detail: "Senha incorreta." });
    }
    if (!TAREFAS.has(tarefa)) return res.status(400).json({ detail: "Tarefa desconhecida." });

    const r = await disparar(tarefa);
    if (!r.ok) {
      const corpo = await r.json().catch(() => ({}));
      return res.status(502).json({ detail: `O GitHub recusou o pedido (${r.status}): ${corpo.message || "sem detalhe"}` });
    }
    return res.status(202).json({ ok: true });
  } catch (erro) {
    return res.status(502).json({ detail: `Falha ao falar com o GitHub: ${erro.message}` });
  }
}
