// Sobe a API Python (FastAPI) com o Python da .venv e a reinicia quando
// algum arquivo .py em src/ muda. O reinício é feito aqui (e não pelo
// --reload do uvicorn), porque no Windows o worker antigo do uvicorn às
// vezes não encerra e continua servindo o código velho.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, watch } from "node:fs";
import { join } from "node:path";

const raiz = join(import.meta.dirname, "..");
const windows = process.platform === "win32";
const python = windows
  ? join(raiz, ".venv", "Scripts", "python.exe")
  : join(raiz, ".venv", "bin", "python");

if (!existsSync(python)) {
  console.error(`Python da .venv não encontrado em ${python}.`);
  console.error("Crie a venv: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt");
  process.exit(1);
}

const args = ["-m", "uvicorn", "src.web.api:app", "--host", "127.0.0.1", "--port", "8000"];
let processo = null;
let encerrando = false;

function iniciar() {
  processo = spawn(python, args, {
    cwd: raiz, stdio: "inherit", env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  processo.on("exit", (codigo) => {
    if (encerrando) process.exit(codigo ?? 0);
  });
}

function parar() {
  if (!processo || processo.exitCode !== null) return;
  if (windows) {
    spawnSync("taskkill", ["/pid", String(processo.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    processo.kill("SIGTERM");
  }
}

let espera = null;
watch(join(raiz, "src"), { recursive: true }, (_evento, arquivo) => {
  if (!arquivo || !arquivo.endsWith(".py")) return;
  clearTimeout(espera);
  espera = setTimeout(() => {
    console.log(`\n[api] ${arquivo} mudou — reiniciando a API…`);
    const antigo = processo;
    parar();
    // Espera o processo antigo liberar a porta antes de subir o novo.
    const subir = () => (antigo.exitCode === null ? setTimeout(subir, 100) : iniciar());
    subir();
  }, 300);
});

for (const sinal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sinal, () => { encerrando = true; parar(); process.exit(0); });
}
process.on("exit", parar);

iniciar();
