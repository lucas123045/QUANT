import { useState } from "react";
import { useApi } from "../api.js";
import { Cartao, Estado } from "../ui.jsx";

const dinheiro = (n) => n != null && Number.isFinite(Number(n))
  ? Number(n).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "—";
const percentual = (n, casas = 1) => n != null && Number.isFinite(Number(n))
  ? `${(Number(n) * 100).toLocaleString("pt-BR", { maximumFractionDigits: casas })}%` : "—";

function CalculadoraComposta() {
  const [valor, setValor] = useState(1000);
  const [aporte, setAporte] = useState(200);
  const [taxa, setTaxa] = useState(0.8);
  const [meses, setMeses] = useState(24);
  const principal = Math.max(0, Number(valor) || 0);
  const mensal = Math.max(0, Number(aporte) || 0);
  const juros = Math.max(-99, Number(taxa) || 0) / 100;
  const prazo = Math.min(600, Math.max(0, Number(meses) || 0));
  let saldo = principal;
  for (let i = 0; i < prazo; i += 1) saldo = saldo * (1 + juros) + mensal;
  const aportado = principal + mensal * prazo;
  return (
    <Cartao titulo="Calculadora 1 · juros compostos" className="estudo-calculadora">
      <p>O saldo cresce sobre o valor inicial, os aportes e os juros que já foram acumulados. A taxa é uma hipótese que você escolhe, não uma previsão.</p>
      <div className="estudo-campos">
        <label>Valor inicial (R$)<input type="number" min="0" value={valor} onChange={(e) => setValor(e.target.value)} /></label>
        <label>Aporte mensal (R$)<input type="number" min="0" value={aporte} onChange={(e) => setAporte(e.target.value)} /></label>
        <label>Taxa ao mês (%)<input type="number" step="0.1" value={taxa} onChange={(e) => setTaxa(e.target.value)} /></label>
        <label>Prazo (meses)<input type="number" min="0" max="600" value={meses} onChange={(e) => setMeses(e.target.value)} /></label>
      </div>
      <div className="estudo-resultado"><span>Saldo matemático</span><strong>{dinheiro(saldo)}</strong>
        <small>{dinheiro(aportado)} aportados · {dinheiro(saldo - aportado)} de diferença pela taxa hipotética</small></div>
      <small className="sutil">Cálculo mensal simplificado, com aporte no fim de cada mês. Não inclui impostos, tarifas nem inflação.</small>
    </Cartao>
  );
}

function CalculadoraQueda() {
  const [valor, setValor] = useState(10000);
  const [queda, setQueda] = useState(20);
  const inicial = Math.max(0, Number(valor) || 0);
  const percentualQueda = Math.min(99.9, Math.max(0, Number(queda) || 0));
  const restante = inicial * (1 - percentualQueda / 100);
  const recuperacao = restante > 0 ? inicial / restante - 1 : null;
  return (
    <Cartao titulo="Calculadora 2 · queda e recuperação" className="estudo-calculadora">
      <p>Uma perda e a recuperação necessária não têm a mesma porcentagem: depois da queda, o ganho incide sobre um saldo menor.</p>
      <div className="estudo-campos estudo-campos-duplos">
        <label>Valor antes da queda (R$)<input type="number" min="0" value={valor} onChange={(e) => setValor(e.target.value)} /></label>
        <label>Queda (%)<input type="number" min="0" max="99.9" step="0.1" value={queda} onChange={(e) => setQueda(e.target.value)} /></label>
      </div>
      <div className="estudo-metricas">
        <div><span>Valor depois da queda</span><strong>{dinheiro(restante)}</strong></div>
        <div><span>Perda em reais</span><strong>{dinheiro(inicial - restante)}</strong></div>
        <div><span>Alta necessária para voltar</span><strong>{recuperacao == null ? "—" : percentual(recuperacao)}</strong></div>
      </div>
    </Cartao>
  );
}

function ExemploQUANT({ dados }) {
  const estrategia = dados?.carteiras?.estrategia;
  const ibovespa = dados?.carteiras?.ibovespa;
  const capital = dados?.capital_inicial ?? 100000;
  return (
    <Cartao titulo="Os números observados no QUANT">
      <p>Estes valores vêm da simulação apresentada na aba Carteira. São uma fotografia do histórico disponível, não uma promessa de repetição.</p>
      {estrategia && ibovespa ? (
        <div className="estudo-metricas">
          <div><span>Capital inicial simulado</span><strong>{dinheiro(capital)}</strong></div>
          <div><span>Patrimônio da estratégia</span><strong>{dinheiro(estrategia.patrimonio)} <small>({percentual(estrategia.retorno_acumulado)} no período)</small></strong></div>
          <div><span>Ibovespa no mesmo período</span><strong>{dinheiro(ibovespa.patrimonio)} <small>({percentual(ibovespa.retorno_acumulado)})</small></strong></div>
          <div><span>Estratégia em ações, em média</span><strong>{percentual(estrategia.exposicao_media)}</strong></div>
          <div><span>Maior queda da estratégia</span><strong>{percentual(estrategia.drawdown_maximo)}</strong></div>
          <div><span>Oscilação anualizada da estratégia</span><strong>{percentual(estrategia.volatilidade_anualizada)}</strong></div>
        </div>
      ) : <p className="sutil">Ainda não há histórico de preços suficiente para exibir números da simulação. Os conceitos abaixo continuam válidos.</p>}
    </Cartao>
  );
}

export default function Estudos({ base }) {
  const { dados, erro, carregando } = useApi(`/api/simulacao?base=${base}`);
  return (
    <div className="estudos">
      <section className="estudos-abertura">
        <span className="estudos-etiqueta">Guia do zero · sem pré-requisitos</span>
        <h2>Entenda a economia por trás dos números</h2>
        <p>Este guia explica os conceitos que aparecem no QUANT, como a simulação mede resultados e o que os números não permitem concluir.</p>
      </section>
      <Estado carregando={carregando} erro={erro}>
        <ExemploQUANT dados={dados} />
      </Estado>

      <div className="estudos-grade">
        <Cartao titulo="1. Dinheiro no tempo">
          <p><strong>Capital</strong> é o dinheiro inicial disponível. No QUANT, a carteira começa com {dinheiro(dados?.capital_inicial ?? 100000)} em uma simulação fictícia. <strong>Retorno</strong> mede a mudança em relação ao começo:</p>
          <div className="estudo-formula">retorno = (valor final ÷ valor inicial) − 1</div>
          <p>Se R$ 100.000 viram R$ 105.000, o retorno é 5%. Isso não diz quanto você ganhou por mês, nem considera automaticamente inflação ou impostos.</p>
        </Cartao>
        <Cartao titulo="2. Juros compostos">
          <p>Quando o rendimento fica aplicado, os períodos seguintes rendem também sobre os ganhos anteriores. Com taxa mensal constante, o saldo cresce multiplicando-se por <code>(1 + taxa)</code> a cada mês.</p>
          <p>Na vida real, ações não pagam uma taxa mensal fixa. A calculadora abaixo serve para entender a matemática de uma hipótese.</p>
        </Cartao>
        <Cartao titulo="3. Ações e risco">
          <p>Uma ação representa uma fração de uma empresa. Seu preço pode subir ou cair por expectativas, resultados, juros, câmbio e muitos outros fatores. Uma notícia positiva não garante que o preço suba.</p>
          <p>O QUANT simula compras e vendas com preços históricos ajustados por proventos. A simulação usa dinheiro fictício; ela não envia ordens ao mercado.</p>
        </Cartao>
        <Cartao titulo="4. Exposição: quanto está investido">
          <p><strong>Exposição</strong> é a parte do patrimônio aplicada em ações. O restante fica em caixa. A regra pode investir até 20% do patrimônio por ação, então a estratégia pode permanecer parcialmente em dinheiro.</p>
          <p>Caixa tende a variar menos que ações. Por isso, menor oscilação pode apenas significar que menos dinheiro ficou exposto ao mercado — não que a estratégia escolheu melhor os ativos.</p>
        </Cartao>
        <Cartao titulo="5. Oscilação e volatilidade">
          <p>A volatilidade resume o quanto os retornos diários variaram. O sistema calcula o desvio padrão diário e anualiza por uma convenção de 252 pregões.</p>
          <div className="estudo-formula">volatilidade anualizada = desvio padrão diário × √252</div>
          <p>Ela não indica a direção do próximo movimento. Uma oscilação baixa não elimina a possibilidade de perda.</p>
        </Cartao>
        <Cartao titulo="6. Queda máxima">
          <p>O <strong>drawdown</strong> compara o patrimônio com o pico anterior. A queda máxima é o pior recuo observado entre um pico e um vale no período.</p>
          <p>Uma queda de 20% exige alta de 25% para voltar ao ponto inicial. A calculadora mostra essa relação com qualquer valor.</p>
        </Cartao>
        <Cartao titulo="7. Referência de comparação">
          <p>O <strong>benchmark</strong> é uma referência para comparação. O QUANT usa o Ibovespa. Comparar períodos diferentes ou carteiras com exposições diferentes pode confundir a leitura.</p>
          <p>Por isso a tela também informa quanto ficou investido. O Ibovespa da simulação permanece 100% exposto; a estratégia pode manter parte em caixa.</p>
        </Cartao>
        <Cartao titulo="8. Inflação, CDI e retorno real">
          <p>Inflação reduz o que o dinheiro compra. O retorno descontada a inflação é o <strong>retorno real</strong>, aproximadamente retorno nominal menos inflação quando ambos são pequenos.</p>
          <p>O CDI é uma taxa de referência comum para renda fixa. Ele não é uma ação nem uma promessa de rendimento; comparar com ele exige o mesmo período e considerar impostos e custos.</p>
        </Cartao>
        <Cartao titulo="9. Probabilidade da IA">
          <p>O percentual mostrado pela IA é a confiança declarada pelo modelo, não uma chance comprovada de acerto. Por exemplo, 80% de confiança não significa que acertará 8 em cada 10 vezes.</p>
          <p>Calibração compara essa confiança com os acertos observados em muitos casos. O escore de Brier resume o erro: quanto menor, melhor; sem amostra suficiente, ele também é incerto.</p>
        </Cartao>
        <Cartao titulo="10. Custos, impostos e limites">
          <p>Corretagem, emolumentos e diferença entre preço esperado e executado reduzem o retorno. No projeto, os custos configurados estão zerados até haver valores aprovados. Impostos não são modelados.</p>
          <p>Histórico curto, poucos eventos, viés de sobrevivência e possível conhecimento do LLM sobre o passado limitam as conclusões. Resultado histórico não prevê o futuro e não é recomendação de investimento.</p>
        </Cartao>
      </div>
      <div className="estudos-calculadoras"><CalculadoraComposta /><CalculadoraQueda /></div>
    </div>
  );
}
