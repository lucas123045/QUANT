import { useEffect, useState } from "react";
import { useApi, formatarData } from "../api.js";
import { Cartao, Estado, Tickers } from "../ui.jsx";

const CARTEIRA = ["PETR4", "VALE3", "ITUB4", "BBDC4", "ABEV3"];

export default function Noticias({ base }) {
  const [ticker, setTicker] = useState("");
  const [busca, setBusca] = useState("");
  const [buscaAplicada, setBuscaAplicada] = useState("");
  const [soCarteira, setSoCarteira] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setBuscaAplicada(busca), 300);
    return () => clearTimeout(t);
  }, [busca]);

  const params = new URLSearchParams({ base, so_carteira: soCarteira });
  if (ticker) params.set("ticker", ticker);
  if (buscaAplicada) params.set("q", buscaAplicada);
  const { dados, erro, carregando, recarregar } = useApi(`/api/noticias?${params}`);

  return (
    <Cartao titulo={dados ? `${dados.total} notícia(s)` : "Notícias"}
      acao={<button className="botao-link" onClick={recarregar}>Atualizar</button>}>
      <div className="filtros">
        <input type="search" placeholder="Buscar no título ou texto…" value={busca}
          onChange={(e) => setBusca(e.target.value)} />
        <select value={ticker} onChange={(e) => setTicker(e.target.value)}>
          <option value="">Todas as empresas</option>
          {CARTEIRA.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <label className="caixa">
          <input type="checkbox" checked={soCarteira} onChange={(e) => setSoCarteira(e.target.checked)} />
          Só as que mencionam a carteira
        </label>
      </div>

      <Estado carregando={carregando && !dados} erro={erro} vazio={dados && !dados.itens.length}
        mensagemVazio="Nenhuma notícia. Rode a coleta na página Ações.">
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
      </Estado>
    </Cartao>
  );
}
