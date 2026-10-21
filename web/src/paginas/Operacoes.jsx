import { useState } from "react";
import { useApi, formatarData, plural } from "../api.js";
import { Cartao, Criterios, Estado, Etiqueta, EtiquetaDecisao, EtiquetaSentimento } from "../ui.jsx";

const REGRA_VIGENTE = "REGRA_V2";
// Linhas gravadas antes da REGRA_V2 não registravam a versão: eram da V1.
const versao = (op) => op.versao_regra || "REGRA_V1";

export default function Operacoes({ base }) {
  const { dados, erro, carregando, recarregar } = useApi(`/api/operacoes?base=${base}`);
  const [aberta, setAberta] = useState(null);

  return (
    <Cartao titulo={dados ? `Log de auditoria · ${plural(dados.length, "operação", "operações")}` : "Log de auditoria"}
      acao={<button className="botao-link" onClick={recarregar}>Atualizar</button>}>
      <p className="nota">
        Registro append-only (data/operacoes.jsonl): nada é apagado. Cada linha guarda o evento com o trecho da fonte,
        a classificação, o modelo, a versão do prompt e da regra, os critérios conferidos, a decisão e a explicação.
        Toque numa decisão para ver por que ela foi tomada.
      </p>
      <Estado carregando={carregando && !dados} erro={erro} vazio={dados && !dados.length}
        mensagemVazio="Nenhuma compra ou venda registrada ainda.">
        <ul className="lista-operacoes">
          {dados?.map((op, i) => {
            const chave = `${op.data}-${op.ticker}-${i}`;
            return (
              <li key={chave} className={aberta === chave ? "aberta" : ""}>
                <button className="operacao-linha" onClick={() => setAberta(aberta === chave ? null : chave)}>
                  <span>{formatarData(op.data + "T12:00:00-03:00", false)}</span>
                  <span className="ticker">{op.ticker}</span>
                  <EtiquetaDecisao decisao={op.decisao} />
                  <EtiquetaSentimento classificacao={op.classificacao} />
                  <span className="sutil truncar">
                    {versao(op) !== REGRA_VIGENTE && <Etiqueta>{versao(op).replace("REGRA_", "")}</Etiqueta>} {op.evento?.resumo}
                  </span>
                  <span className="seta">{aberta === chave ? "▾" : "▸"}</span>
                </button>
                {aberta === chave && (
                  <div className="operacao-detalhe">
                    <div className="porque">
                      <h4>Por que a regra decidiu {op.decisao === "compra" ? "comprar" : "vender"}</h4>
                      <Criterios criterios={op.criterios} versao={versao(op)} />
                    </div>
                    <dl className="lista-chave-valor">
                      <dt>Regra</dt>
                      <dd>
                        {versao(op).replace("_", " ")}
                        {versao(op) !== REGRA_VIGENTE && " · anterior à revisão, fora da carteira atual"}
                      </dd>
                      <dt>Classificação (IA)</dt><dd><EtiquetaSentimento classificacao={op.classificacao} /></dd>
                      <dt>Motivo (regra)</dt><dd>{op.motivo}</dd>
                      <dt>Trecho da fonte</dt><dd><blockquote>“{op.evento?.trecho_fonte}”</blockquote></dd>
                      <dt>Origem</dt>
                      <dd>
                        {op.evento?.origem?.fonte} · {formatarData(op.evento?.origem?.timestamp_publicacao)} ·{" "}
                        <a href={op.evento?.origem?.url} target="_blank" rel="noreferrer">abrir notícia</a>
                      </dd>
                      <dt>Modelo / prompt</dt><dd>{op.modelo} · {op.versao_prompt}</dd>
                    </dl>
                    <pre className="relatorio">{op.explicacao}</pre>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </Estado>
    </Cartao>
  );
}
