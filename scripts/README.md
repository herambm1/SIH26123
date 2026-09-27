# scripts/ — one-command startup

Owner: Member 6

| Your shell | Run |
|---|---|
| Git Bash / WSL / macOS / Linux | `bash scripts/run_all.sh` |
| Plain Windows PowerShell (no Git Bash/WSL) | `powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1` |

Both start the Python FastAPI simulation engine (`http://localhost:8001`) and
the Java Spring Boot backend (`http://localhost:8080`) together. Neither
starts the dashboard — `run_all.sh`/`run_all.ps1` is not "inherently
Windows-incompatible" so much as bash itself not existing on a bare Windows
install; pick the script matching your actual shell rather than assuming one
"just works" everywhere. Run the dashboard yourself in a separate terminal:

```
cd dashboard
npm install
npm run dev
```

Then open `http://localhost:5173`.

For a containerized alternative (simulation + backend only, no dashboard —
see `docker-compose.yml`'s own header comment for why), from the repo root:

```
docker-compose up
```
