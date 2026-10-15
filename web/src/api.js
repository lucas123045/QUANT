import { useCallback, useEffect, useState } from "react";

export async function pedir(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    throw new Error(corpo?.detail || `Erro ${resposta.status}`);
  }
  return corpo;
}

/** Carrega um endpoint e recarrega quando o caminho muda. */
export function useApi(caminho) {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(() => {
    if (!caminho) return;
    setCarregando(true);
    pedir(caminho)
      .then((d) => { setDados(d); setErro(null); })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [caminho]);

  useEffect(recarregar, [recarregar]);
  return { dados, erro, carregando, recarregar };
}

export function formatarData(iso, comHora = true) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit", month: "2-digit", year: "numeric",
    ...(comHora ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function formatarNumero(valor, casas = 2, minimo = 0) {
  if (valor === null || valor === undefined) return "—";
  if (typeof valor !== "number") return String(valor);
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: minimo, maximumFractionDigits: casas });
}

export function formatarPreco(valor) {
  return formatarNumero(valor, 2, 2);
}
