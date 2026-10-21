"""Sincronização com os dados da nuvem (ramo "dados"), com um ZIP montado no teste."""
import io
import zipfile

from src import sincronizar


def zip_do_ramo(arquivos: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("QUANT-dados/", "")
        for nome, conteudo in arquivos.items():
            z.writestr(f"QUANT-dados/{nome}", conteudo)
    return buffer.getvalue()


def test_junta_traz_e_preserva(tmp_path):
    (tmp_path / "arquivo").mkdir()
    (tmp_path / "arquivo" / "2026-10-20.jsonl").write_text('{"id": "a"}\n{"id": "so-local"}\n', encoding="utf-8")
    (tmp_path / "execucoes" / "2026-10-20").mkdir(parents=True)
    (tmp_path / "execucoes" / "2026-10-20" / "resumo.json").write_text('{"versao": "local"}', encoding="utf-8")
    (tmp_path / "agendamento.log").write_text("log local", encoding="utf-8")

    r = sincronizar.sincronizar(tmp_path, zip_do_ramo({
        "arquivo/2026-10-20.jsonl": '{"id": "a"}\n{"id": "da-nuvem"}\n',
        "execucoes/2026-10-20/resumo.json": '{"versao": "nuvem"}',
        "operacoes.jsonl": '{"op": 1}\n',
        "agendamento.log": "log da nuvem",
    }))

    linhas = (tmp_path / "arquivo" / "2026-10-20.jsonl").read_text(encoding="utf-8").splitlines()
    assert linhas == ['{"id": "a"}', '{"id": "da-nuvem"}', '{"id": "so-local"}']  # nada local se perde
    assert '"nuvem"' in (tmp_path / "execucoes" / "2026-10-20" / "resumo.json").read_text(encoding="utf-8")
    assert (tmp_path / "operacoes.jsonl").exists()
    assert (tmp_path / "agendamento.log").read_text(encoding="utf-8") == "log local"  # nunca tocado
    assert r == {"novos": 1, "atualizados": 1, "unidos": 1}


def test_rodar_de_novo_nao_muda_nada(tmp_path):
    conteudo = zip_do_ramo({"operacoes.jsonl": '{"op": 1}\n'})
    sincronizar.sincronizar(tmp_path, conteudo)
    assert sincronizar.sincronizar(tmp_path, conteudo) == {"novos": 0, "atualizados": 0, "unidos": 0}


def test_ignora_caminhos_que_escapam_da_pasta(tmp_path):
    destino = tmp_path / "data"
    sincronizar.sincronizar(destino, zip_do_ramo({"../fora.txt": "x"}))
    assert not (tmp_path / "fora.txt").exists()
