// Gera a vitrine estática (web/public/dados/) com o Python da .venv.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const raiz = join(import.meta.dirname, "..");
const python = process.platform === "win32"
  ? join(raiz, ".venv", "Scripts", "python.exe")
  : join(raiz, ".venv", "bin", "python");

if (!existsSync(python)) {
  console.error(`Python da .venv não encontrado em ${python}.`);
  process.exit(1);
}
const r = spawnSync(python, ["-m", "src.web.exportar"], {
  cwd: raiz, stdio: "inherit", env: { ...process.env, PYTHONIOENCODING: "utf-8" },
});
process.exit(r.status ?? 1);
