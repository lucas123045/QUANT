import { useEffect, useState } from "react";
import Painel from "./paginas/Painel.jsx";
import Noticias from "./paginas/Noticias.jsx";
import Execucoes from "./paginas/Execucoes.jsx";
import Operacoes from "./paginas/Operacoes.jsx";
import Acoes from "./paginas/Acoes.jsx";
import Configuracao from "./paginas/Configuracao.jsx";

const PAGINAS = [
  { id: "painel", nome: "Painel", icone: "◧", componente: Painel },
  { id: "noticias", nome: "Notícias", icone: "≡", componente: Noticias },
  { id: "execucoes", nome: "Execuções", icone: "▤", componente: Execucoes },
  { id: "operacoes", nome: "Operações", icone: "⇅", componente: Operacoes },
  { id: "acoes", nome: "Ações", icone: "▶", componente: Acoes },
  { id: "configuracao", nome: "Configuração", icone: "⚙", componente: Configuracao },
];

function lerPreferencia(chave, padrao) {
  try { return localStorage.getItem(chave) || padrao; } catch { return padrao; }
}

function gravarPreferencia(chave, valor) {
  try { localStorage.setItem(chave, valor); } catch { /* sem armazenamento: ignora */ }
}

export default function App() {
  const [pagina, setPagina] = useState(() => {
    const hash = window.location.hash.slice(1);
    return PAGINAS.some((p) => p.id === hash) ? hash : "painel";
  });
  const [base, setBase] = useState(() => lerPreferencia("quant.base", "real"));
  const [menuAberto, setMenuAberto] = useState(false);

  useEffect(() => { window.location.hash = pagina; }, [pagina]);
  useEffect(() => gravarPreferencia("quant.base", base), [base]);

  const atual = PAGINAS.find((p) => p.id === pagina);
  const Pagina = atual.componente;

  return (
    <div className="app">
      <aside className={`lateral ${menuAberto ? "aberta" : ""}`}>
        <div className="marca">
          <span className="marca-logo">Q</span>
          <div>
            <strong>QUANT</strong>
            <small>notícias → eventos → decisão</small>
          </div>
        </div>
        <nav>
          {PAGINAS.map((p) => (
            <button key={p.id} className={`nav-item ${p.id === pagina ? "ativo" : ""}`}
              onClick={() => { setPagina(p.id); setMenuAberto(false); }}>
              <span className="nav-icone">{p.icone}</span>{p.nome}
            </button>
          ))}
        </nav>
        <p className="lateral-rodape">
          O LLM extrai e explica. Quem decide é a regra determinística (strategy.py).
        </p>
      </aside>

      <div className="principal">
        <header className="topo">
          <button className="menu-botao" onClick={() => setMenuAberto((v) => !v)} aria-label="Menu">☰</button>
          <h1>{atual.nome}</h1>
          <div className="alternador" role="group" aria-label="Base de dados">
            <button className={base === "real" ? "ativo" : ""} onClick={() => setBase("real")}>
              Dados reais
            </button>
            <button className={base === "teste" ? "ativo" : ""} onClick={() => setBase("teste")}>
              Modo de teste
            </button>
          </div>
        </header>
        {base === "teste" && (
          <div className="faixa-teste">
            Você está vendo os dados do <strong>modo de teste</strong> (notícias de exemplo e LLM falso).
            Não use nada daqui em conclusões do trabalho.
          </div>
        )}
        <main className="conteudo">
          <Pagina base={base} irPara={setPagina} />
        </main>
      </div>
    </div>
  );
}
