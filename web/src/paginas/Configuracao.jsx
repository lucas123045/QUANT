import { useApi, formatarNumero } from "../api.js";
import { Cartao, Estado } from "../ui.jsx";

function Tabela({ valores }) {
  return (
    <table className="tabela-config">
      <tbody>
        {Object.entries(valores).map(([chave, valor]) => (
          <tr key={chave}>
            <th>{chave}</th>
            <td>
              {valor === null
                ? <span className="pendente">PENDENTE</span>
                : Array.isArray(valor) ? valor.join(" → ")
                : typeof valor === "number" ? formatarNumero(valor, 4)
                : String(valor)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Configuracao() {
  const { dados, erro, carregando } = useApi("/api/config");
  return (
    <Estado carregando={carregando} erro={erro}>
      {dados && (
        <div className="pilha">
          <div className="aviso tom-alerta">
            Somente leitura. Parâmetros da regra, do critério e os períodos só mudam no código
            (src/config.py), com aprovação do autor e antes do congelamento.
          </div>
          <div className="grade">
            <Cartao titulo="Regra de decisão (REGRA_V1)"><Tabela valores={dados.regra} /></Cartao>
            <Cartao titulo="Critério de sucesso"><Tabela valores={dados.criterio} /></Cartao>
            <Cartao titulo="Períodos e congelamento"><Tabela valores={dados.periodos} /></Cartao>
            <Cartao titulo="Custos (frações do valor negociado)"><Tabela valores={dados.custos} /></Cartao>
            <Cartao titulo="Outros parâmetros" className="span-2"><Tabela valores={dados.outros} /></Cartao>
            <Cartao titulo="Fontes RSS">
              <ul className="lista-simples">
                {dados.fontes_rss.map((f) => <li key={f.url}><strong>{f.nome}</strong> <span className="sutil">{f.url}</span></li>)}
              </ul>
            </Cartao>
            <Cartao titulo="Casamento de tickers" className="span-3">
              <div className="tabela-rolagem">
                <table>
                  <thead><tr><th>Ticker</th><th>Aliases aceitos</th><th>Exclusões</th></tr></thead>
                  <tbody>
                    {Object.entries(dados.aliases).map(([t, lista]) => (
                      <tr key={t}>
                        <td><span className="ticker">{t}</span></td>
                        <td>{lista.join(", ")}</td>
                        <td>{(dados.exclusoes[t] || []).join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="nota">"vale" sozinho nunca indica VALE3; só com contexto ("a Vale", "da Vale", "Vale S.A.").</p>
            </Cartao>
          </div>
        </div>
      )}
    </Estado>
  );
}
