import { useApi, formatarNumero } from "../api.js";
import { Cartao, Estado } from "../ui.jsx";

// Identificadores (semente, contagens técnicas) não levam separador de milhar.
const SEM_SEPARADOR = new Set(["SEMENTE_BASELINE_2"]);

/** Nome de parâmetro que pode quebrar linha depois de cada "_" (e não no meio da palavra). */
function NomeParametro({ nome }) {
  const partes = nome.split("_");
  return partes.map((p, i) => (
    <span key={i}>{p}{i < partes.length - 1 && <>_<wbr /></>}</span>
  ));
}

function Tabela({ valores }) {
  return (
    <table className="tabela-config">
      <tbody>
        {Object.entries(valores).map(([chave, valor]) => (
          <tr key={chave}>
            <th><NomeParametro nome={chave} /></th>
            <td>
              {valor === null
                ? <span className="pendente">PENDENTE</span>
                : Array.isArray(valor) ? valor.join(" → ")
                : typeof valor === "number" ? (SEM_SEPARADOR.has(chave) ? String(valor) : formatarNumero(valor, 4))
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
            <Cartao titulo={`Regra de decisão (${dados.versao_regra || "REGRA_V3"})`}><Tabela valores={dados.regra} /></Cartao>
            <Cartao titulo="Critério de sucesso"><Tabela valores={dados.criterio} /></Cartao>
            <Cartao titulo="Períodos e congelamento"><Tabela valores={dados.periodos} /></Cartao>
            <Cartao titulo="Custos da pesquisa (frações do valor negociado)"><Tabela valores={dados.custos} /></Cartao>
            <Cartao titulo="Outros parâmetros" className="span-2"><Tabela valores={dados.outros} /></Cartao>
            {dados.pratica && (
              <Cartao titulo="Camada prática (fora da pesquisa)" className="span-2">
                <Tabela valores={dados.pratica} />
                <p className="nota">
                  Usados só na página "Na prática": custos da B3, imposto de renda, tamanho pelo risco, limite por setor e saídas.
                  Não alteram a regra nem o critério do trabalho. Fontes e justificativas em src/config.py.
                </p>
              </Cartao>
            )}
            <Cartao titulo="Fontes RSS">
              <ul className="lista-simples">
                {dados.fontes_rss.map((f) => (
                  <li key={f.url}><strong>{f.nome}</strong> · {f.feed === "geral" ? "geral" : f.feed} <span className="sutil">{f.url}</span></li>
                ))}
                <li><strong>CVM</strong> · fatos relevantes <span className="sutil">dados.cvm.gov.br (documentos IPE, por CNPJ)</span></li>
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
