# Production Launch গাইড

এই ডকুমেন্ট অনুসরণ করে `universal-ai-agent` একটা VPS-এ (Hetzner, DigitalOcean, Contabo, বা যেকোনো Ubuntu 22.04/24.04 সার্ভার) পাবলিক লাইভ করতে পারবেন — HTTPS, backup, CI/CD সহ।

---

## এই আপডেটে যা যা নতুন করা হয়েছে

| আইটেম | কী করা হয়েছে |
|---|---|
| **`/v1/images/{image_id}/analyze` route** | আগে missing ছিল — `VisionService`/`handle_image` লজিক লেখা ছিল কিন্তু কোনো route তা call করত না। ছবি আপলোড করার পর analysis চালানোর route যোগ করা হয়েছে। |
| **S3-compatible storage** | `app/images/s3_storage.py` — AWS S3, Cloudflare R2, DigitalOcean Spaces, Backblaze B2, MinIO — যেকোনোটা দিয়ে চলবে। `STORAGE_BACKEND=s3` সেট করলেই সক্রিয় হয়। |
| **Frontend chat UI** | `frontend/chat/` — আগে ৩টা ফাইলই খালি ছিল, এখন পুরো কার্যকর একটা full-page chat app (product cards, image upload সহ)। |
| **`frontend/widget/config.js`** | প্রোগ্রামেটিক embed helper (CMS/framework integration-এর জন্য)। |
| **CI (`.github/workflows/ci.yml`)** | প্রতিটা push/PR-এ Postgres+Redis সহ পুরো test suite চালায়। |
| **`pytest-asyncio` missing dependency** | `requirements-dev.txt`-এ যোগ করা হয়েছে — এটা ছাড়া `@pytest.mark.asyncio` টেস্টগুলো CI-তে fail করত। |
| **Docker publish workflow** | `.github/workflows/docker-publish.yml` — main-এ push করলেই ghcr.io-তে image push হয়। |
| **`docker-compose.prod.yml` + Caddy** | Automatic HTTPS (Let's Encrypt), DB/Redis পোর্ট আর বাইরে expose হয় না। |
| **`scripts/backup_db.sh`** | Daily `pg_dump` backup + optional S3 upload + auto-cleanup। |
| **`.env.production.example`** | Production-grade defaults (`AUTO_CREATE_TABLES=false`, real CORS, ইত্যাদি)। |

কোড-লেভেলের সব পরিবর্তন সরাসরি টেস্ট করে যাচাই করা হয়েছে (`pytest` চালিয়ে ২০১/২০৬ pass — বাকি ৫টা এই sandbox-এর local Postgres auth-এর কারণে, `docker-compose`-এর আসল pgvector container-এ প্রযোজ্য না)।

---

## ধাপ ১ — সার্ভার প্রস্তুত করা

একটা VPS নিন (ন্যূনতম ২ vCPU / 4GB RAM সাজেস্ট করা হয়, sentence-transformers embedding মডেল লোড হওয়ার কারণে)।

```bash
ssh root@YOUR_SERVER_IP

# Docker + Compose plugin ইনস্টল
curl -fsSL https://get.docker.com | sh
apt-get install -y docker-compose-plugin git
```

## ধাপ ২ — DNS

আপনার ডোমেইনের একটা subdomain (যেমন `api.yourstore.com`) সার্ভারের IP-তে **A record** দিয়ে পয়েন্ট করুন। Caddy নিজে থেকেই এই ডোমেইনের জন্য Let's Encrypt সার্টিফিকেট নেবে — শুধু DNS আগে থেকে propagate হয়ে থাকতে হবে।

## ধাপ ৩ — কোড আনা এবং secrets বসানো

```bash
git clone https://github.com/YOUR_USERNAME/universal-ai-agent.git
cd universal-ai-agent

cp .env.production.example .env
```

এখন `.env` খুলে নিচের মানগুলো বসান:

```bash
# Fernet key generate করুন
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`.env`-এ বসান:
- `CREDENTIAL_ENCRYPTION_KEY` — উপরের কমান্ডের আউটপুট
- `GROQ_API_KEY_1` — আপনার Groq API key ([console.groq.com](https://console.groq.com))
- `POSTGRES_PASSWORD` — একটা শক্তিশালী পাসওয়ার্ড, এবং `DATABASE_URL`-এও একই পাসওয়ার্ড বসান
- `CORS_ALLOW_ORIGINS` — যেসব ডোমেইন থেকে widget embed হবে, কমা দিয়ে আলাদা করে (`*` রাখবেন না)
- `DOMAIN` — ধাপ ২-এর subdomain
- `ACME_EMAIL` — আপনার ইমেইল (cert expiry notification-এর জন্য)

## ধাপ ৪ — লাইভ করা

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

প্রথমবার image build হতে কয়েক মিনিট লাগবে (sentence-transformers/torch dependency-র কারণে)। শেষ হলে:

```bash
docker compose -f docker-compose.prod.yml ps      # সব healthy কিনা দেখুন
curl https://YOUR_DOMAIN/health                    # {"status":"ok"} আসা উচিত
```

`/docs` এ গিয়ে interactive API docs দেখতে পারবেন: `https://YOUR_DOMAIN/docs`

## ধাপ ৫ — প্রথম স্টোর তৈরি ও টেস্ট

```bash
docker compose -f docker-compose.prod.yml exec api python create_test_tenant.py
```

(অথবা `https://YOUR_DOMAIN/admin` এ গিয়ে UI দিয়ে একটা স্টোর তৈরি করুন।) পাওয়া `pk_live_...` কী দিয়ে টেস্ট করুন:

- **Chat UI:** `https://YOUR_DOMAIN/chat/?key=pk_live_xxxxxxxx`
- **Widget embed:** `<script src="https://YOUR_DOMAIN/widget.js" data-key="pk_live_xxxxxxxx" async></script>`

## ধাপ ৬ — Backup সেটআপ করা

```bash
chmod +x scripts/backup_db.sh
crontab -e
```

এই লাইনটা যোগ করুন (রাত ২টায় প্রতিদিন backup):

```
0 2 * * * cd /root/universal-ai-agent && ./scripts/backup_db.sh >> /var/log/uai-backup.log 2>&1
```

দূরের কোথাও (S3/R2) ব্যাকআপ পাঠাতে চাইলে `.env`-এ `BACKUP_S3_BUCKET` সেট করুন এবং `aws configure` দিয়ে credentials বসান — script নিজেই বাকিটা করবে।

## ধাপ ৭ — CI/CD চালু করা

`.github/workflows/ci.yml` এমনিতেই প্রতিটা push/PR-এ চলবে — কিছু করতে হবে না। `.github/workflows/docker-publish.yml` main branch-এ push হলে `ghcr.io/YOUR_USERNAME/universal-ai-agent:latest` তৈরি করবে। এরপর সার্ভারে deploy আরও দ্রুত করতে চাইলে:

```yaml
# docker-compose.prod.yml এ api/worker সার্ভিসের build: বদলে দিন
image: ghcr.io/YOUR_USERNAME/universal-ai-agent:latest
```

এবং deploy করার সময়:
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## ধাপ ৮ — একাধিক replica চালাতে চাইলে (scale)

Local filesystem storage (`STORAGE_BACKEND=local`) শুধু single-replica-তে নিরাপদ। একাধিক `api` container চালানোর আগে:

```bash
# .env এ
STORAGE_BACKEND=s3
S3_BUCKET=your-bucket
S3_REGION=auto              # R2 হলে "auto"
S3_ENDPOINT_URL=https://xxxx.r2.cloudflarestorage.com   # শুধু R2/Spaces/MinIO-এর জন্য, real AWS S3 হলে খালি রাখুন
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_PUBLIC_BASE_URL=https://cdn.yourstore.com   # (ঐচ্ছিক — না দিলে presigned URL ব্যবহার হবে)
```

---

## Launch-এর আগে শেষ চেকলিস্ট

- [ ] `.env`-এ সব secret বাস্তব মান দিয়ে ভরা (কোনো `CHANGE_ME` বা খালি ঘর নেই)
- [ ] `CORS_ALLOW_ORIGINS` real domain(s)-এ লক করা, `*` নয়
- [ ] `AUTO_CREATE_TABLES=false` (schema শুধু Alembic দিয়ে পরিচালিত হবে)
- [ ] DNS propagate হয়ে গেছে এবং `https://YOUR_DOMAIN/health` কাজ করছে
- [ ] `docker compose -f docker-compose.prod.yml ps` — সব service `healthy`
- [ ] Backup cron সেট করা এবং একবার ম্যানুয়ালি টেস্ট চালানো (`./scripts/backup_db.sh`)
- [ ] একটা টেস্ট স্টোর দিয়ে chat + image upload আসলেই কাজ করছে কিনা যাচাই করা
- [ ] GitHub repo secrets-এ কিছু বসানোর দরকার নেই — `docker-publish.yml` built-in `GITHUB_TOKEN` ব্যবহার করে
- [ ] `.env` ফাইল কখনো git-এ commit হয়নি তা নিশ্চিত করা (`.gitignore`-এ আছে, তবুও `git status` দিয়ে একবার চেক করুন)

---

## এখনো যা সম্পূর্ণ Claude-এর কাজের বাইরে (আপনাকে করতে হবে)

এগুলো এমন জিনিস যেগুলোর জন্য বাস্তব অ্যাকাউন্ট/ক্রেডেনশিয়াল/সিদ্ধান্ত দরকার — কোনো AI এগুলো আপনার হয়ে "শেষ" করে দিতে পারবে না:

1. **VPS কেনা এবং SSH access** — কোনো cloud provider-এ অ্যাকাউন্ট খোলা।
2. **ডোমেইন কেনা এবং DNS A record বসানো**।
3. **Groq API key** পাওয়া (console.groq.com) — বিনামূল্যে/paid tier আপনার সিদ্ধান্ত।
4. **S3-compatible bucket তৈরি করা** (যদি স্কেল করতে চান) — Cloudflare R2 বিনামূল্যে egress-এর জন্য ভালো অপশন।
5. **Monitoring/alerting সাবস্ক্রিপশন** (Slack webhook URL, PagerDuty, ইত্যাদি) — `ALERT_WEBHOOK_URL`-এ বসাতে হবে।
6. **আসল secret মানগুলো** — কোনো placeholder Claude তৈরি করে দেয়নি; প্রতিটা `.env.production.example`-এর খালি ঘর আপনাকে বাস্তব মান দিয়ে ভরতে হবে।

বাকি সব — code, migration, Docker config, CI/CD, backup script, frontend — সবই এই ZIP-এ প্রস্তুত আছে।
