import { useEffect, useState } from "react";
import { useApi, formatarData, plural } from "../api.js";
import { Cartao, Estado, Tickers } from "../ui.jsx";

// Notícias por página. A coleta traz ~20 por dia: sem paginação, a lista
// passaria do limite da API em poucas semanas e as mais antigas sumiriam.
const POR_PAGINA = 100;

function tempoDesde(iso) {
  const minutos = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutos < 1) return "agora há pouco";
  if (minutos < 60) return `há ${minutos} min`;
  const horas = Math.round(minutos / 60);
  return horas < 48 ? `há ${horas} h` : `há ${Math.round(horas / 24)} dias`;
}

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
  // A coleta agendada roda de hora em hora: a página confere a cada 5 minutos.
  const { dados, erro, carregando, recarregar } = useApi(`/api/noticias?${params}`, 5 * 60 * 1000);
  const filtrando = Boolean(ticker || buscaAplicada || soCarteira);
  const faltam = dados ? dados.total - dados.itens.length : 0;
  const coleta = dados?.ultima_coleta;

  return (
    <Cartao titulo={dados ? plural(dados.total, "notícia", "notícias") : "Notícias"}
      acao={<button className="botao-link" onClick={recarregar}>Atualizar</button>}>
      {coleta && (
        <p className={`ultima-coleta ${Date.now() - new Date(coleta.quando).getTime() > 3 * 3600_000 ? "atrasada" : ""}`}>
          Última coleta: {formatarData(coleta.quando)} ({tempoDesde(coleta.quando)}) ·{" "}
          {coleta.novos ? plural(coleta.novos, "notícia nova", "notícias novas") : "nenhuma notícia nova"}
          {Date.now() - new Date(coleta.quando).getTime() > 3 * 3600_000 && " · a coleta automática parece parada"}
        </p>
      )}
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
