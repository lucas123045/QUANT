import { useEffect, useState } from "react";
import Icone from "./icones.jsx";
import { VITRINE, pedir } from "./api.js";
import Simulacao from "./paginas/Simulacao.jsx";
import Painel from "./paginas/Painel.jsx";
import Noticias from "./paginas/Noticias.jsx";
import Execucoes from "./paginas/Execucoes.jsx";
import Operacoes from "./paginas/Operacoes.jsx";
import Acoes from "./paginas/Acoes.jsx";
import Configuracao from "./paginas/Configuracao.jsx";

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
    fetch("/dados/meta.json").then((r) => (r.ok ? r.json() : null)).then(setMeta).catch(() => setMeta(null));
  }, []);
  const quando = meta?.gerado_em
    ? new Date(meta.gerado_em).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : null;
  return (
    <div className="faixa-vitrine">
      <Icone nome="info" tamanho={16} />
      <span className="so-desktop">
        <strong>Versão online, somente leitura.</strong>{" "}
        {quando ? `Dados atualizados em ${quando}.` : meta === null ? "Dados ainda não publicados." : ""}{" "}
        A coleta de notícias e a análise pela IA rodam no computador do autor.
      </span>
      <span className="so-celular">
        <strong>Somente leitura</strong>
        {quando ? ` · dados de ${quando.replace(/\/\d{4},/, ",")}` : ""}
      </span>
    </div>
  );
}

function Relogio() {
  const [agora, setAgora] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setAgora(new Date()), 30000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="relogio">
      <Icone nome="relogio" tamanho={15} />
      {agora.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", weekday: "short", day: "2-digit", month: "short" })}
      {" · "}
      {agora.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" })}
    </span>
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
    gravarPreferencia("quant.tema", tema);
  }, [tema]);

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

        {VITRINE && <FaixaVitrine />}
        {base === "teste" && (
          <div className="faixa-teste">
            <Icone nome="frasco" tamanho={16} />
            Você está vendo o <strong>modo de teste</strong>: notícias de exemplo e IA simulada. Nada daqui vale como resultado.
          </div>
        )}

        <main className="conteudo">
          <Pagina base={base} irPara={setPagina} />
        </main>

        <nav className="nav-inferior" aria-label="Navegação principal">
          {NAV_INFERIOR.map(([id, nome, icone]) => (
            <button key={id} className={id === pagina ? "ativo" : ""} onClick={() => setPagina(id)}>
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
