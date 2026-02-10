# Deployment Guide - Agentic System Builder

## Prerequisites

Before deploying, ensure you have:

1. **Google Gemini API Key** 
   - Get free key at: https://makersuite.google.com/app/apikey
   - Free tier includes 1500 requests/day

2. **Vercel Account** (Free)
   - Sign up at: https://vercel.com

3. **Optional: Supabase Account** (Free)
   - Sign up at: https://supabase.com
   - For cloud database (otherwise uses SQLite)

## Deployment Steps

### Option 1: Vercel CLI (Recommended)

1. **Install Vercel CLI**
```bash
npm install -g vercel
```

2. **Login to Vercel**
```bash
vercel login
```

3. **Deploy from project directory**
```bash
cd agentic-system-builder
vercel
```

4. **Add Environment Variables**
During deployment, Vercel will prompt for environment variables. Add:
```
GEMINI_KEY=your_gemini_api_key
JWT_SECRET=generate_random_32_char_string
```

Optional (for Supabase):
```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
```

5. **Deploy to Production**
```bash
vercel --prod
```

### Option 2: Vercel Dashboard

1. **Push to GitHub**
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/agentic-builder.git
git push -u origin main
```

2. **Connect to Vercel**
   - Go to https://vercel.com/new
   - Click "Import Project"
   - Select your GitHub repository
   - Click "Import"

3. **Configure Environment Variables**
   In Vercel dashboard, go to Settings → Environment Variables:
   
   Add these variables:
   - `GEMINI_KEY` = your Gemini API key
   - `JWT_SECRET` = random 32+ character string
   - `SUPABASE_URL` = (optional) your Supabase project URL
   - `SUPABASE_KEY` = (optional) your Supabase anon key

4. **Deploy**
   - Click "Deploy"
   - Wait for build to complete
   - Your app will be live at: https://your-project.vercel.app

## Environment Variables Setup

### Required Variables

1. **GEMINI_KEY**
   ```
   Get from: https://makersuite.google.com/app/apikey
   Format: AIza...your_key_here
   ```

2. **JWT_SECRET**
   ```
   Generate using Python:
   python -c "import secrets; print(secrets.token_hex(32))"
   
   Or online: https://generate-secret.vercel.app/32
   Format: Any random string, minimum 32 characters
   ```

### Optional Variables

3. **SUPABASE_URL**
   ```
   Get from: Supabase Dashboard → Settings → API
   Format: https://xxxxxxxxxxxxx.supabase.co
   ```

4. **SUPABASE_KEY**
   ```
   Get from: Supabase Dashboard → Settings → API → anon/public key
   Format: eyJ...your_key_here
   ```

## Post-Deployment

### 1. Test Your Deployment

Visit your Vercel URL and test:
- Registration
- Login
- Project creation
- System generation
- ZIP download

### 2. Monitor

Check Vercel dashboard for:
- Deployment logs
- Function execution times
- Error tracking
- Usage metrics

### 3. Custom Domain (Optional)

1. Go to Vercel Dashboard → Settings → Domains
2. Add your custom domain
3. Update DNS records as instructed
4. SSL certificate auto-generated

## Troubleshooting

### Build Failures

**Error: Requirements installation failed**
```
Solution: Check requirements.txt for version conflicts
Verify Python version is 3.9+
```

**Error: Module not found**
```
Solution: Add missing module to requirements.txt
Redeploy after updating
```

### Runtime Errors

**Error: GEMINI_KEY not found**
```
Solution: Add GEMINI_KEY to Vercel environment variables
Redeploy after adding
```

**Error: Database locked**
```
Solution: Use Supabase instead of SQLite for production
Set SUPABASE_URL and SUPABASE_KEY
```

**Error: Function timeout**
```
Solution: System generation can take time
Free tier has 10s timeout
Upgrade to Pro for 60s timeout
Or use Supabase for async processing
```

### Performance Issues

**Slow response times**
```
Solution: 
- Gemini API can be slow on free tier
- Consider caching responses
- Use Supabase for better database performance
```

## Scaling Considerations

### Free Tier Limits

**Vercel Free:**
- 100GB bandwidth/month
- 100 function invocations/day
- 10s function timeout

**Gemini Free:**
- 1500 requests/day
- 15 requests/minute

**Supabase Free:**
- 500MB database
- 2GB bandwidth
- 50,000 monthly active users

### Upgrading

When you exceed free tier:

1. **Vercel Pro** ($20/month)
   - Unlimited bandwidth
   - 60s function timeout
   - Analytics

2. **Gemini Paid** (Pay-per-use)
   - Higher rate limits
   - Better performance
   - SLA guarantees

3. **Supabase Pro** ($25/month)
   - 8GB database
   - 50GB bandwidth
   - Daily backups

## Security Best Practices

1. **Never commit .env file**
   - Already in .gitignore
   - Use Vercel environment variables

2. **Rotate JWT_SECRET regularly**
   - Update in Vercel dashboard
   - Invalidates all existing tokens

3. **Monitor API usage**
   - Check Gemini quota
   - Set up alerts

4. **Rate limiting**
   - Already implemented in code
   - Adjust limits in app.py if needed

## Backup Strategy

### Database Backup (if using Supabase)

1. Supabase auto-backups daily
2. Manual backup: Dashboard → Database → Backups
3. Download as SQL file

### Code Backup

1. Keep GitHub repository updated
2. Tag releases: `git tag v1.0.0`
3. Vercel keeps deployment history

## Monitoring & Logs

### Vercel Logs

```bash
# Real-time logs
vercel logs

# Function logs
vercel logs --follow
```

### Error Tracking

Consider adding (optional):
- Sentry for error tracking
- LogRocket for user sessions
- PostHog for analytics

## Support

If you encounter issues:

1. Check Vercel deployment logs
2. Verify all environment variables
3. Test Gemini API key separately
4. Check rate limits
5. Review troubleshooting section

---

**Deployment checklist:**
- [ ] Gemini API key obtained
- [ ] JWT secret generated
- [ ] Vercel account created
- [ ] Code pushed to GitHub
- [ ] Project imported to Vercel
- [ ] Environment variables configured
- [ ] First deployment successful
- [ ] Registration tested
- [ ] System generation tested
- [ ] Custom domain configured (optional)

Good luck with your deployment! 🚀
