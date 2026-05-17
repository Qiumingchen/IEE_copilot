# Compose Contract

The local stack is accepted when:

1. `docker compose up --build` starts postgres, redis, minio, api, worker, and web.
2. `GET http://localhost:8000/health` returns `{"status":"ok"}`.
3. `GET http://localhost:8000/health/db` returns `{"database":"ok"}`.
4. `http://localhost:3000` renders the web dashboard or redirects to login.
5. Searching `microbial transglutaminase` returns an enzyme summary and a job id.
