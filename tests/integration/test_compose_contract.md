# Compose Contract

The local stack is accepted when:

1. `docker compose up --build` starts postgres, redis, minio, api, worker, and web.
2. `GET http://localhost:8000/health` returns `{"status":"ok"}`.
3. `GET http://localhost:8000/health/db` returns `{"database":"ok"}`.
4. `http://localhost:3000` renders the web dashboard or redirects to login.
5. Searching `microbial transglutaminase` returns an enzyme summary and a job id.

## Manual Verification

Prepare environment:

```powershell
Copy-Item .env.example .env
docker compose config
docker compose up --build
```

Check API health:

```powershell
Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:8000/health/db -UseBasicParsing
```

Check web:

```powershell
Invoke-WebRequest -Uri http://localhost:3000 -UseBasicParsing
```

Expected result: the API returns healthy JSON responses and the web app returns
an HTML dashboard shell.
