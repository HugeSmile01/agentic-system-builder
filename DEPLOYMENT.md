# Deployment Guide

This guide covers deploying the Agentic System Builder to production environments.

## Prerequisites

- Python 3.12+
- Git
- Vercel CLI (for Vercel deployment)
- Google Gemini API key
- (Optional) Supabase account for PostgreSQL database

## Environment Variables

### Required

These environment variables **must** be set before running the application:

| Variable | Description | Example |
|----------|-------------|---------|
| `GEMINI_KEY` | Google Gemini API key | `AIza...` |
| `JWT_SECRET` | JWT signing secret (min 32 chars) | `your-super-secret-jwt-key-here-32-chars-min` |
| `SECRET_KEY` | Flask session secret (min 32 chars) | `your-super-secret-session-key-32-chars-min` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | `*` (all origins) |
| `SUPABASE_URL` | Supabase project URL | None (uses SQLite) |
| `SUPABASE_KEY` | Supabase anon key | None (uses SQLite) |
| `DATA_ROOT` | Directory for generated files | `./generated` |
| `SQLITE_PATH` | SQLite database path | `./data/agentic.db` |

## Local Development

### 1. Clone and Install

```bash
git clone https://github.com/HugeSmile01/agentic-system-builder.git
cd agentic-system-builder
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:
- `GEMINI_KEY`
- `JWT_SECRET` (generate with: `python -c "import secrets; print(secrets.token_hex(32))"`)
- `SECRET_KEY` (generate with: `python -c "import secrets; print(secrets.token_hex(32))"`)

### 3. Run

```bash
python app.py
```

Visit http://localhost:5000

## Production Deployment

### Vercel (Recommended)

#### 1. Install Vercel CLI

```bash
npm i -g vercel
```

#### 2. Deploy

```bash
vercel --prod
```

#### 3. Configure Environment Variables

In your Vercel dashboard, add these environment variables:

- `GEMINI_KEY`
- `JWT_SECRET`
- `SECRET_KEY`
- `ALLOWED_ORIGINS` (set to your production domain, e.g., `https://yourdomain.com`)

**Important for Production:**
- Set `ALLOWED_ORIGINS` to your specific domain to prevent CSRF attacks
- Use Supabase or another persistent database (SQLite on Vercel is ephemeral)

#### 4. Database Setup (Supabase Recommended)

For production, SQLite is not recommended as Vercel's file system is ephemeral. Use Supabase:

1. Create a free Supabase account at https://supabase.com
2. Create a new project
3. Add these environment variables in Vercel:
   - `SUPABASE_URL`: Your project URL (e.g., `https://xxx.supabase.co`)
   - `SUPABASE_KEY`: Your anon/public key

The database schema will be created automatically on first run.

### Railway

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Add environment variables
railway variables set GEMINI_KEY=your_key_here
railway variables set JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
railway variables set SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
railway variables set ALLOWED_ORIGINS=https://yourdomain.com

# Deploy
railway up
```

### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
```

Build and run:

```bash
docker build -t agentic-builder .
docker run -p 5000:5000 \
  -e GEMINI_KEY=your_key \
  -e JWT_SECRET=your_jwt_secret \
  -e SECRET_KEY=your_secret_key \
  agentic-builder
```

## Security Checklist

Before deploying to production:

- [ ] Set `ALLOWED_ORIGINS` to specific domains (not `*`)
- [ ] Generate strong, unique secrets for `JWT_SECRET` and `SECRET_KEY` (min 32 characters)
- [ ] Use HTTPS (Vercel provides this automatically)
- [ ] Use a persistent database (Supabase recommended)
- [ ] Review rate limits in `app.py` (adjust based on your needs)
- [ ] Enable monitoring and logging
- [ ] Set up regular database backups

## Database Migrations

The application automatically creates necessary tables on startup. For schema changes:

1. Backup your database
2. Update `_SCHEMA_SQL` in `lib/database.py`
3. Deploy the new version
4. The new tables/indexes will be created automatically

## Monitoring

### Health Check

```bash
curl https://your-domain.com/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-14T06:00:00.000Z",
  "gemini_configured": true,
  "supabase_configured": true,
  "database": "connected",
  "version": "3.1.1"
}
```

### Logs

- **Vercel**: View logs in the Vercel dashboard
- **Railway**: `railway logs`
- **Local**: Check console output

## Troubleshooting

### "GEMINI_KEY must be set" error
- Ensure `GEMINI_KEY` is set in your environment variables
- For Vercel, check the Environment Variables section in your project settings

### "JWT_SECRET must be at least 32 characters" error
- Generate a new secret: `python -c "import secrets; print(secrets.token_hex(32))"`
- Set it in your environment variables

### Database connection errors
- If using SQLite on Vercel, switch to Supabase for persistence
- Check that `SUPABASE_URL` and `SUPABASE_KEY` are correctly set

### CORS errors
- Set `ALLOWED_ORIGINS` to include your frontend domain
- Format: `https://yourdomain.com` or multiple: `https://domain1.com,https://domain2.com`

## Performance Optimization

1. **Database Indexes**: Already configured in `lib/database.py`
2. **Rate Limiting**: Configured per endpoint, adjust in `app.py`
3. **Caching**: Consider adding Redis for session storage
4. **CDN**: Serve static files through a CDN
5. **Database Pooling**: Use Supabase's connection pooling

## Support

For issues and questions:
- GitHub Issues: https://github.com/HugeSmile01/agentic-system-builder/issues
- Email: Contact the maintainer

---

**Last Updated**: February 2026  
**Author**: John Rish Ladica, Student Leader at SLSU-HC – Society of Information Technology Students (SITS)
