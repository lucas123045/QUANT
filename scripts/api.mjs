// Sobe a API Python (FastAPI) usando o Python da .venv do projeto.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const raiz = join(import.meta.dirname, "..");
const python = process.platform === "win32"
  ? join(raiz, ".venv", "Scripts", "python.exe")
  : join(raiz, ".venv", "bin", "python");

if (!existsSync(python)) {
  console.error(`Python da .venv não encontrado em ${python}.`);
  console.error("Crie a venv: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt");
  process.exit(1);
}

const args = ["-m", "uvicorn", "src.web.api:app", "--host", "127.0.0.1", "--port", "8000",
  "--reload", "--reload-dir", "src"];
const processo = spawn(python, args, { cwd: raiz, stdio: "inherit",
  env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
processo.on("exit", (codigo) => process.exit(codigo ?? 0));
