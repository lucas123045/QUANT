import { useEffect, useState } from "react";
import Icone from "./icones.jsx";
import { VITRINE, lerArquivo, pedir, useApi } from "./api.js";
import Simulacao from "./paginas/Simulacao.jsx";
import Painel from "./paginas/Painel.jsx";
import Noticias from "./paginas/Noticias.jsx";
import Execucoes from "./paginas/Execucoes.jsx";
import Operacoes from "./paginas/Operacoes.jsx";
import Acoes from "./paginas/Acoes.jsx";
import Configuracao from "./paginas/Configuracao.jsx";
import Estudos from "./paginas/Estudos.jsx";

const PAGINAS = [
  { id: "carteira", nome: "Minha carteira", icone: "carteira", componente: Simulacao,
    titulo: "Bem-vindo de volta", subtitulo: "Sua carteira simulada, com dinheiro fictício e preços reais" },
  { id: "painel", nome: "Visão do sistema", icone: "painel", componente: Painel,
    titulo: "Visão do sistema", subtitulo: "Status, funil de notícias e pendências da pesquisa" },
  { id: "noticias", nome: "Notícias", icone: "noticias", componente: Noticias,
    titulo: "Notícias", subtitulo: "Tudo o que foi coletado dos portais" },
  { id: "execucoes", nome: "Análises do dia", icone: "execucoes", componente: Execucoes,
    titulo: "Análises do dia", subtitulo: "O que a IA leu e o que a regra decidiu, dia a dia" },
  { id: "operacoes", nome: "Decisões", icone: "operacoes", componente: Operacoes,
    titulo: "Decisões registradas", subtitulo: "Compras e vendas, com a notícia e o motivo" },
  { id: "acoes", nome: "Rodar agora", icone: "acoes", componente: Acoes,
    titulo: "Rodar agora", subtitulo: "Coletar notícias e analisar com a IA" },
  { id: "configuracao", nome: "Configuração", icone: "configuracao", componente: Configuracao,
    titulo: "Configuração", subtitulo: "Parâmetros da regra (somente leitura)" },
  { id: "estudos", nome: "Estudos", icone: "estudos", componente: Estudos,
    titulo: "Estudos", subtitulo: "Economia e conceitos por trás do QUANT" },
];

// Barra inferior do celular (as demais páginas ficam em "Mais").
const NAV_INFERIOR = [
  ["carteira", "Carteira", "carteira"],
  ["noticias", "Notícias", "noticias"],
  ["execucoes", "Análises", "execucoes"],
  ["operacoes", "Decisões", "operacoes"],
];

function lerPreferencia(chave, padrao) {
  try { return localStorage.getItem(chave) || padrao; } catch { return padrao; }
}

function gravarPreferencia(chave, valor) {
  try { localStorage.setItem(chave, valor); } catch { /* sem armazenamento: ignora */ }
}

const TEMPO_MINIMO_ABERTURA = 1200;  // ms: dá tempo de a animação do logo terminar

/** Some com a tela de abertura (index.html) quando os primeiros dados chegam. */
function useFecharAbertura() {
  useEffect(() => {
    const abertura = document.getElementById("abertura");
    if (!abertura) return undefined;
    let cancelado = false;
    const espera = new Promise((r) => setTimeout(r, TEMPO_MINIMO_ABERTURA));
    const dados = Promise.race([
      pedir("/api/status").catch(() => null),
      new Promise((r) => setTimeout(r, 6000)),  // nunca prende a pessoa na abertura
    ]);
    Promise.all([espera, dados]).then(() => {
      if (cancelado) return;
      abertura.classList.add("saindo");
      setTimeout(() => abertura.remove(), 600);
    });
    return () => { cancelado = true; };
  }, []);
}

function FaixaVitrine() {
  const [meta, setMeta] = useState(undefined);  // undefined = carregando; null = não publicado
  useEffect(() => {
    lerArquivo("meta.json").then(setMeta).catch(() => setMeta(null));
  }, []);
  const quando = meta?.gerado_em
    ? new Date(meta.gerado_em).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : null;
  const idadeBruta = meta?.gerado_em ? Date.now() - new Date(meta.gerado_em).getTime() : 0;
  const idadeMs = Number.isFinite(idadeBruta) ? idadeBruta : 0;
  const horas = Math.max(0, Math.floor(idadeMs / 3_600_000));
  // A coleta na nuvem roda a cada 30 min: mais de 3 h sem atualizar é sinal de problema.
  const velha = idadeMs > 3 * 3_600_000;
  const atraso = horas >= 48 ? `há ${Math.floor(horas / 24)} dias` : `há ${horas} h`;
  return (
    <div className={`faixa-vitrine ${velha ? "velha" : ""}`}>
      <Icone nome="info" tamanho={16} />
      <span className="so-desktop">
        <strong>Versão online, somente leitura.</strong>{" "}
        {quando ? `Dados atualizados em ${quando}${velha ? ` (${atraso} — desatualizados)` : ""}.` : meta === null ? "Dados ainda não publicados." : ""}{" "}
        A coleta de notícias e a análise pela IA rodam sozinhas na nuvem, a cada 30 minutos.
      </span>
      <span className="so-celular">
        <strong>Somente leitura</strong>
        {quando ? ` · dados de ${quando.replace(/\/\d{4},/, ",")}${velha ? ` (${atraso})` : ""}` : ""}
      </span>
    </div>
  );
}

/** Pregão da B3 aberto? Aproximação: dias úteis, 10h às 18h de Brasília (sem feriados). */
function pregaoAberto(agora) {
  const partes = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Sao_Paulo", weekday: "short", hour: "numeric", hourCycle: "h23",
  }).formatToParts(agora).map((p) => [p.type, p.value]));
  const hora = Number(partes.hour);
  return !["Sat", "Sun"].includes(partes.weekday) && hora >= 10 && hora < 18;
}

function Relogio() {
  const [agora, setAgora] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setAgora(new Date()), 30000);
    return () => clearInterval(id);
  }, []);
  const aberto = pregaoAberto(agora);
  return (
    <span className="relogio">
      <span className={`ponto-vivo ${aberto ? "aberto" : ""}`} title={aberto ? "Pregão aberto (aprox.)" : "Pregão fechado"} />
      {agora.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", weekday: "short", day: "2-digit", month: "short" })}
      {" · "}
      {agora.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" })}
      <span className="relogio-pregao">{aberto ? "pregão aberto" : "pregão fechado"}</span>
    </span>
  );
}

/**
 * Fita de cotações, no estilo de terminal de mercado: as ações da carteira com
 * preço e variação do dia, rolando devagar (para ao passar o mouse). Mesmo dado
 * da Carteira (/api/simulacao); some se ainda não houver preço.
 */
function FitaCotacoes({ base }) {
  const { dados } = useApi(`/api/simulacao?base=${base}`, 5 * 60 * 1000);
  const ativos = (dados?.ativos || []).filter((a) => a.preco != null);
  if (!ativos.length) return null;
  const item = (a, i) => (
    <span key={`${a.ticker}-${i}`} className="fita-item">
      <strong>{a.ticker}</strong>
      <span>R$ {a.preco.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
      {a.variacao_dia != null && (
        <span className={a.variacao_dia > 0 ? "sobe" : a.variacao_dia < 0 ? "desce" : ""}>
          {a.variacao_dia > 0 ? "▲" : a.variacao_dia < 0 ? "▼" : "•"} {Math.abs(a.variacao_dia * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%
        </span>
      )}
    </span>
  );
  return (
    <div className="fita" aria-label="Cotações das ações da carteira">
      {/* Duas cópias idênticas lado a lado: ao rolar metade, a rolagem volta ao início sem emenda. */}
      <div className="fita-trilho">
        <span className="fita-grupo">{ativos.map(item)}</span>
        <span className="fita-grupo" aria-hidden="true">{ativos.map((a, i) => item(a, i + ativos.length))}</span>
      </div>
    </div>
  );
}

export default function App() {
  const [pagina, setPagina] = useState(() => {
    const hash = window.location.hash.slice(1);
    return PAGINAS.some((p) => p.id === hash) ? hash : "carteira";
  });
  const [base, setBase] = useState(() => lerPreferencia("quant.base", "real"));
  const [tema, setTema] = useState(() => lerPreferencia("quant.tema", "escuro"));
  const [menuAberto, setMenuAberto] = useState(false);

  useEffect(() => {
    if (window.location.hash.slice(1) !== pagina) window.location.hash = pagina;
    window.scrollTo(0, 0);
  }, [pagina]);
  // Segue o endereço: botão "voltar" do navegador/celular e links com #pagina.
  useEffect(() => {
    const aoMudar = () => {
      const id = window.location.hash.slice(1);
      if (PAGINAS.some((p) => p.id === id)) setPagina(id);
    };
    window.addEventListener("hashchange", aoMudar);
    return () => window.removeEventListener("hashchange", aoMudar);
  }, []);
  useEffect(() => gravarPreferencia("quant.base", base), [base]);
  useEffect(() => {
    document.documentElement.dataset.tema = tema;
    // Barra do navegador/app no celular acompanha o fundo do tema.
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", tema === "claro" ? "#d5cfc2" : "#0b0d0c");
    gravarPreferencia("quant.tema", tema);
  }, [tema]);
  // Esc fecha o menu lateral do celular.
  useEffect(() => {
    if (!menuAberto) return undefined;
    const aoTeclar = (e) => { if (e.key === "Escape") setMenuAberto(false); };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [menuAberto]);

  useFecharAbertura();

  const atual = PAGINAS.find((p) => p.id === pagina);
  const Pagina = atual.componente;

  return (
    <div className="app">
      <aside className={`lateral ${menuAberto ? "aberta" : ""}`}>
        <div className="marca">
          <span className="marca-logo"><Icone nome="alta" tamanho={18} /></span>
          <strong>QUANT</strong>
        </div>
        <nav>
          {PAGINAS.map((p) => (
            <button key={p.id} className={`nav-item ${p.id === pagina ? "ativo" : ""}`}
              aria-current={p.id === pagina ? "page" : undefined}
              onClick={() => { setPagina(p.id); setMenuAberto(false); }}>
              <Icone nome={p.icone} />{p.nome}
            </button>
          ))}
        </nav>

        <div className="lateral-rodape">
          <div className="lateral-bloco">
            <span className="lateral-rotulo">Dados</span>
            <div className="segmentado">
              <button className={base === "real" ? "ativo" : ""} onClick={() => setBase("real")}>Reais</button>
              <button className={base === "teste" ? "ativo" : ""} onClick={() => setBase("teste")}>Teste</button>
            </div>
          </div>
          <button className="botao-tema" onClick={() => setTema(tema === "escuro" ? "claro" : "escuro")}>
            <Icone nome={tema === "escuro" ? "sol" : "lua"} tamanho={16} />
            {tema === "escuro" ? "Tema claro" : "Tema escuro"}
          </button>
          <div className="lateral-perfil">
            <span className="avatar">R$</span>
            <div><strong>Carteira fictícia</strong><small>sem dinheiro real</small></div>
          </div>
        </div>
      </aside>
      {menuAberto && <div className="veu" onClick={() => setMenuAberto(false)} />}

      <div className="principal">
        <header className="topo">
          <span className="topo-logo so-celular"><Icone nome="alta" tamanho={16} /></span>
          <div className="topo-titulo">
            <h1>{atual.titulo}</h1>
            <p>{atual.subtitulo}</p>
          </div>
          <Relogio />
          <button className="topo-perfil so-celular" onClick={() => setMenuAberto(true)} aria-label="Abrir menu">
            <Icone nome="configuracao" tamanho={18} />
          </button>
        </header>

        <FitaCotacoes base={base} />
        {VITRINE && <FaixaVitrine />}
        {base === "teste" && (
          <div className="faixa-teste">
            <Icone nome="frasco" tamanho={16} />
            {/* Um único item flexível: senão cada trecho de texto vira uma coluna. */}
            <span>Você está vendo o <strong>modo de teste</strong>: notícias de exemplo e IA simulada. Nada daqui vale como resultado.</span>
          </div>
        )}

        <main className="conteudo">
          {/* A chave reinicia a animação de entrada a cada troca de página ou de base. */}
          <div key={`${pagina}-${base}`} className="pagina-entra">
            <Pagina base={base} irPara={setPagina} />
          </div>
        </main>

        <nav className="nav-inferior" aria-label="Navegação principal">
          {NAV_INFERIOR.map(([id, nome, icone]) => (
            <button key={id} className={id === pagina ? "ativo" : ""} aria-current={id === pagina ? "page" : undefined}
              onClick={() => setPagina(id)}>
              <Icone nome={icone} tamanho={21} /><span>{nome}</span>
            </button>
          ))}
          <button className={NAV_INFERIOR.some(([id]) => id === pagina) ? "" : "ativo"} onClick={() => setMenuAberto(true)}>
            <Icone nome="painel" tamanho={21} /><span>Mais</span>
          </button>
        </nav>

        <footer className="rodape">
          A IA lê as notícias e explica as decisões; quem decide comprar ou vender é uma regra fixa e auditável.
          Simulação com dinheiro fictício — não é recomendação de investimento.
        </footer>
      </div>
    </div>
  );
}
