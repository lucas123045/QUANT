import { formatarData, formatarNumero, formatarPreco, useApi } from "../api.js";
import { Cartao, dia, pct, tom } from "../comum.jsx";
import { COR_TICKER } from "../graficos.jsx";
import Icone from "../icones.jsx";
import { Estado, Etiqueta } from "../ui.jsx";

const hora = (iso) => new Date(iso).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });

const ICONES_AGENDA = { copom: "escudo", resultado: "grafico", provento: "dinheiro" };

function diasAte(iso) {
  const hoje = new Date(new Date().toLocaleDateString("en-CA", { timeZone: "America/Sao_Paulo" }) + "T00:00:00");
  const n = Math.round((new Date(iso + "T00:00:00") - hoje) / 86_400_000);
  return n === 0 ? "hoje" : n === 1 ? "amanhã" : `em ${n} dias`;
}

function Indicador({ rotulo, valor, detalhe }) {
  return (
    <section className="f-estat">
      <span className="f-estat-valor">{valor}</span>
      <span className="f-estat-rotulo">{rotulo}</span>
      {detalhe && <small>{detalhe}</small>}
    </section>
  );
}

function Macro({ m, c }) {
  const i = m.indicadores;
  const s = i.selic;
  const it = c.itens || {};
  const variacao = (x) => (x?.variacao_30d == null ? null : `${pct(x.variacao_30d)} em 30 dias`);
  return (
    <div className="mercado-indicadores">
      <Indicador rotulo="Selic (meta)" valor={s ? `${formatarNumero(s.valor, 2)}%` : "—"}
        detalhe={s ? `desde ${dia(s.desde)}${s.anterior != null ? `, antes ${formatarNumero(s.anterior, 2)}%` : ""}` : "Banco Central sem resposta"} />
      <Indicador rotulo="Inflação (IPCA 12 meses)" valor={i.ipca_12m ? `${formatarNumero(i.ipca_12m.valor, 2)}%` : "—"}
        detalhe={i.ipca_12m ? `referência ${formatarData(i.ipca_12m.data + "T12:00:00-03:00", false).slice(3)}` : null} />
      <Indicador rotulo="Juro real aproximado" valor={s && i.ipca_12m ? `${formatarNumero(((1 + s.valor / 100) / (1 + i.ipca_12m.valor / 100) - 1) * 100, 2)}%` : "—"}
        detalhe="Selic descontada a inflação: o que a renda fixa paga de verdade" />
      <Indicador rotulo="Dólar" valor={it.dolar?.valor ? `R$ ${formatarPreco(it.dolar.valor)}` : "—"} detalhe={variacao(it.dolar)} />
      <Indicador rotulo="Petróleo Brent" valor={it.brent?.valor ? `US$ ${formatarPreco(it.brent.valor)}` : "—"}
        detalhe={[variacao(it.brent), "pesa em PETR4"].filter(Boolean).join(" · ")} />
      <Indicador rotulo="Minério de ferro" valor={it.minerio?.valor ? `US$ ${formatarPreco(it.minerio.valor)}` : "—"}
        detalhe={[variacao(it.minerio), "pesa em VALE3"].filter(Boolean).join(" · ")} />
    </div>
  );
}

function NovaYork({ ny }) {
  const aberta = ny.itens.some((i) => i.b3_aberta);
  return (
    <Cartao titulo="Sinal de Nova York" className="f-span-2"
      subtitulo={aberta ? "B3 aberta: o preço local já diz tudo" : "O que os ADRs e o dólar indicam para a próxima abertura da B3"}>
      <Estado vazio={!ny.itens.length} mensagemVazio="Sem cotações intradiárias agora.">
        <ul className="f-lista">
          {ny.itens.map((i) => (
            <li key={i.ticker}>
              <span className="f-ativo-logo pequeno" style={{ background: COR_TICKER[i.ticker] }}>{i.ticker.slice(0, 2)}</span>
              <div>
                <strong>{i.ticker} <span className="sutil">· ADR {i.adr}</span></strong>
                <small>
                  {i.b3_aberta ? "B3 em pregão: vale o preço local"
                    : i.implicita == null ? "sem negócio do ADR depois do fechamento da B3"
                    : `ADR ${pct(i.variacao_adr)} e dólar ${pct(i.variacao_dolar)} desde as ${hora(i.ultimo_negocio_b3)} · ADR às ${hora(i.adr_atualizado)}`}
                </small>
              </div>
              <span className="sutil">{!i.b3_aberta && i.preco_implicito ? `≈ R$ ${formatarPreco(i.preco_implicito)}` : `R$ ${formatarPreco(i.preco_local)}`}</span>
              <strong className={i.b3_aberta ? "" : tom(i.implicita)}>{i.b3_aberta || i.implicita == null ? "—" : pct(i.implicita)}</strong>
            </li>
          ))}
        </ul>
      </Estado>
      <p className="f-nota"><Icone nome="info" tamanho={14} />
        <span>Os ADRs dessas empresas seguem negociando em Nova York depois que a B3 fecha. Variação implícita = (1 + ADR) × (1 + dólar) − 1,
          desde o último negócio na B3. Indica a direção da abertura, não garante o preço.</span>
      </p>
    </Cartao>
  );
}

function Agenda({ a }) {
  return (
    <Cartao titulo="Agenda" subtitulo="O que vem pela frente">
      <Estado vazio={!a.eventos.length} mensagemVazio="Nenhum evento conhecido nas próximas semanas.">
        <ul className="f-lista">
          {a.eventos.slice(0, 10).map((e, k) => (
            <li key={k}>
              <span className={`f-estat-icone ${e.tipo === "copom" ? "tom-alerta" : ""}`}><Icone nome={ICONES_AGENDA[e.tipo] || "relogio"} tamanho={16} /></span>
              <div><strong>{e.titulo}</strong><small>{dia(e.data)} · {e.fonte}</small></div>
              <Etiqueta tom={e.tipo === "copom" ? "alerta" : "neutro"}>{diasAte(e.data)}</Etiqueta>
            </li>
          ))}
        </ul>
      </Estado>
      <p className="f-nota">Em semana de resultado ou de Copom, notícias e preços mudam mais: as decisões merecem mais atenção.</p>
    </Cartao>
  );
}

export default function Mercado() {
  const { dados: d, erro, carregando } = useApi("/api/mercado", 15 * 60 * 1000);
  const avisos = d ? [...d.macro.avisos, ...d.commodities.avisos, ...d.nova_york.avisos, ...d.agenda.avisos] : [];
  return (
    <Estado carregando={carregando && !d} erro={erro}>
      {d && (
        <div className="f-pagina">
          <div className="f-aviso">
            <Icone nome="info" tamanho={16} />
            <span>O contexto que um gestor olha antes de decidir. Nada daqui entra na regra. Atualizado em {formatarData(d.gerado_em)}.</span>
          </div>
          <Macro m={d.macro} c={d.commodities} />
          <div className="f-grade">
            <NovaYork ny={d.nova_york} />
            <Agenda a={d.agenda} />
          </div>
          {!!avisos.length && <p className="f-nota"><Icone nome="info" tamanho={14} /><span>Fontes com problema agora: {avisos.join("; ")}.</span></p>}
          <p className="f-rodape-aviso">Fontes: Banco Central (SGS), Yahoo Finance e calendário do Copom. Datas de resultado e de proventos do Yahoo podem mudar: confira no site de RI da empresa.</p>
        </div>
      )}
    </Estado>
  );
}
