import { useEffect, useState } from "react";
import { useApi, formatarData, plural } from "../api.js";
import { Cartao, Estado, Tickers } from "../ui.jsx";

// Notícias por página. A coleta traz ~20 por dia: sem paginação, a lista
// passaria do limite da API em poucas semanas e as mais antigas sumiriam.
const POR_PAGINA = 100;

export default function Noticias({ base }) {
  const [ticker, setTicker] = useState("");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [soCarteira, setSoCarteira] = useState(false);
  const [limite, setLimite] = useState(POR_PAGINA);
  const status = useApi("/api/status");
  const carteira = status.dados?.carteira ?? [];

  useEffect(() => {
    const t = setTimeout(() => setBuscaAplicada(busca), 300);
    return () => clearTimeout(t);
  }, [busca]);
  // Filtro novo: volta para a primeira página.
  useEffect(() => setLimite(POR_PAGINA), [base, ticker, buscaAplicada, soCarteira]);

  const params = new URLSearchParams({ base, so_carteira: soCarteira, limite });
  if (ticker) params.set("ticker", ticker);
  if (buscaAplicada) params.set("q", buscaAplicada);
  const { dados, erro, carregando, recarregar } = useApi(`/api/noticias?${params}`);
  const filtrando = Boolean(ticker || buscaAplicada || soCarteira);
  const faltam = dados ? dados.total - dados.itens.length : 0;

  return (
    <Cartao titulo={dados ? plural(dados.total, "notícia", "notícias") : "Notícias"}
      acao={<button className="botao-link" onClick={recarregar}>Atualizar</button>}>
      <div className="filtros">
        <input type="search" placeholder="Buscar no título ou texto…" value={busca}
          onChange={(e) => setBusca(e.target.value)} aria-label="Buscar notícias" />
        <select value={ticker} onChange={(e) => setTicker(e.target.value)} aria-label="Filtrar por empresa">
          <option value="">Todas as empresas</option>
          {carteira.map((c) => <option key={c.ticker} value={c.ticker}>{c.ticker} · {c.empresa}</option>)}
        </select>
        <label className="caixa">
          <input type="checkbox" checked={soCarteira} onChange={(e) => setSoCarteira(e.target.checked)} />
          Só as que mencionam a carteira
        </label>
      </div>

      <Estado carregando={carregando && !dados} erro={erro} vazio={dados && !dados.itens.length}
        mensagemVazio={filtrando ? "Nenhuma notícia com esses filtros."
          : "Nenhuma notícia ainda. Rode a coleta na página Rodar agora."}>
        <ul className="lista-noticias">
          {dados?.itens.map((n) => (
            <li key={n.id}>
              <div className="noticia-meta">
                <span>{formatarData(n.timestamp_publicacao)}</span>
                <span className="sutil">{n.fonte}</span>
                <Tickers lista={n.tickers_atuais} />
              </div>
              <a href={n.url} target="_blank" rel="noreferrer" className="noticia-titulo">{n.titulo}</a>
              <p className="noticia-texto">{n.texto}</p>
            </li>
          ))}
        </ul>
        {faltam > 0 && (
          <div className="mais-itens">
            <span className="sutil">Mostrando {dados.itens.length} de {dados.total}</span>
            <button className="botao" disabled={carregando} onClick={() => setLimite(limite + POR_PAGINA)}>
              {carregando ? "Carregando…" : `Mostrar mais ${Math.min(POR_PAGINA, faltam)}`}
            </button>
          </div>
        )}
      </Estado>
    </Cartao>
  );
}
