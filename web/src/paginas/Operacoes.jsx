import { useState } from "react";
import { useApi, formatarData } from "../api.js";
import { Cartao, Estado, EtiquetaDecisao, EtiquetaSentimento } from "../ui.jsx";

export default function Operacoes({ base }) {
  const { dados, erro, carregando, recarregar } = useApi(`/api/operacoes?base=${base}`);
  const [aberta, setAberta] = useState(null);

  return (
    <Cartao titulo={dados ? `Log de auditoria · ${dados.length} operação(ões)` : "Log de auditoria"}
      acao={<button className="botao-link" onClick={recarregar}>Atualizar</button>}>
      <p className="nota">
        Registro append-only (data/operacoes.jsonl). Cada linha guarda o evento com o trecho da fonte,
        a classificação, o modelo, a versão do prompt, a decisão da regra e a explicação.
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
                  <span className="sutil truncar">{op.evento?.resumo}</span>
                  <span className="seta">{aberta === chave ? "▾" : "▸"}</span>
                </button>
                {aberta === chave && (
                  <div className="operacao-detalhe">
                    <dl className="lista-chave-valor">
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
