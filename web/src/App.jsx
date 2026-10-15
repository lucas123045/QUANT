import { useEffect, useState } from "react";
import Painel from "./paginas/Painel.jsx";
import Noticias from "./paginas/Noticias.jsx";
import Execucoes from "./paginas/Execucoes.jsx";
import Operacoes from "./paginas/Operacoes.jsx";
import Simulacao from "./paginas/Simulacao.jsx";
import Acoes from "./paginas/Acoes.jsx";
import Configuracao from "./paginas/Configuracao.jsx";

const PAGINAS = [
  { id: "painel", nome: "Painel", componente: Painel },
  { id: "noticias", nome: "Notícias", componente: Noticias },
  { id: "execucoes", nome: "Execuções", componente: Execucoes },
  { id: "operacoes", nome: "Operações", componente: Operacoes },
  { id: "simulacao", nome: "Simulação", componente: Simulacao },
  { id: "acoes", nome: "Ações", componente: Acoes },
  { id: "configuracao", nome: "Configuração", componente: Configuracao },
];

function lerPreferencia(chave, padrao) {
  try { return localStorage.getItem(chave) || padrao; } catch { return padrao; }
}

function gravarPreferencia(chave, valor) {
  try { localStorage.setItem(chave, valor); } catch { /* sem armazenamento: ignora */ }
}

function Relogio() {
  const [agora, setAgora] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setAgora(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const hora = agora.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const data = agora.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
  return <span className="relogio">SÃO PAULO {data} {hora}</span>;
}

export default function App() {
  const [pagina, setPagina] = useState(() => {
    const hash = window.location.hash.slice(1);
    return PAGINAS.some((p) => p.id === hash) ? hash : "painel";
  });
  const [base, setBase] = useState(() => lerPreferencia("quant.base", "real"));
  const [tema, setTema] = useState(() => lerPreferencia("quant.tema", "escuro"));

  useEffect(() => { window.location.hash = pagina; }, [pagina]);
  useEffect(() => gravarPreferencia("quant.base", base), [base]);
  useEffect(() => {
    document.documentElement.dataset.tema = tema;
    gravarPreferencia("quant.tema", tema);
  }, [tema]);

  const indice = PAGINAS.findIndex((p) => p.id === pagina);
  const Pagina = PAGINAS[indice].componente;

  return (
    <div className="app">
      <header className="barra">
        <div className="barra-linha">
          <div className="marca">
            <span className="marca-quadro" />
            <strong>QUANT</strong>
            <span className="marca-sub">B3 · eventos de notícias</span>
          </div>
          <Relogio />
          <div className="controles">
            <div className="segmentado" role="group" aria-label="Base de dados">
              <button className={base === "real" ? "ativo" : ""} onClick={() => setBase("real")}>Real</button>
              <button className={base === "teste" ? "ativo" : ""} onClick={() => setBase("teste")}>Teste</button>
            </div>
            <button className="botao-tema" onClick={() => setTema(tema === "escuro" ? "claro" : "escuro")}
              title="Alternar tema">
              {tema === "escuro" ? "Claro" : "Escuro"}
            </button>
          </div>
        </div>
        <nav className="abas">
          {PAGINAS.map((p, i) => (
            <button key={p.id} className={p.id === pagina ? "ativa" : ""} onClick={() => setPagina(p.id)}>
              <span className="aba-num">{String(i + 1).padStart(2, "0")}</span>{p.nome}
            </button>
          ))}
        </nav>
      </header>

      {base === "teste" && (
        <div className="faixa-teste">
          MODO DE TESTE — notícias de exemplo e LLM falso. Nada desta base vale para conclusões do trabalho.
        </div>
      )}

      <main className="conteudo">
        <Pagina base={base} irPara={setPagina} />
      </main>

      <footer className="rodape">
        O LLM extrai eventos e explica decisões. Quem decide compra e venda é a regra determinística (strategy.py).
      </footer>
    </div>
  );
}
