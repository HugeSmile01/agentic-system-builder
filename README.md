# Agentic System Builder

> AI-powered autonomous code generation platform that builds complete, deployable software systems through an intelligent multi-agent workflow.

**Author:** John Rish Ladica — Student Leader, SLSU-HC  
**Organization:** Society of Information Technology Students (SITS)

---

## Features

- **Multi-Agent Pipeline** — Planner → Executor → Reviewer → Refactorer workflow
- **AI-Powered Code Generation** — Full-stack applications generated from a text description
- **Quality Assurance** — Automated code review and refactoring before delivery
- **Project Management** — Create, iterate, and track projects with version history
- **Export System** — Download generated projects as ready-to-deploy ZIP archives
- **JWT Authentication** — Secure token-based login and registration
- **Rate Limiting** — Built-in API protection against abuse
- **Mobile-Friendly** — Responsive dark-themed interface

## Tech Stack

| Layer       | Technology             |
| ----------- | ---------------------- |
| Backend     | Python · Flask         |
| Frontend    | HTML · CSS · JavaScript|
| AI          | Google Gemini 1.5 Flash|
| Database    | SQLite (Supabase optional) |
| Auth        | JWT (PyJWT)            |
| Deployment  | Vercel                 |

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/HugeSmile01/agentic-system-builder.git
cd agentic-system-builder
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example file and fill in your keys:

```bash
cp .env.example .env
```

| Variable       | Required | Description                       |
| -------------- | -------- | --------------------------------- |
| `GEMINI_KEY`   | Yes      | Google Gemini API key             |
| `JWT_SECRET`   | Yes      | Random string (32+ characters)    |
| `SUPABASE_URL` | No       | Supabase project URL              |
| `SUPABASE_KEY` | No       | Supabase anon/public key          |

### 3. Run Locally

```bash
python app.py
```

Visit **http://localhost:5000**

### 4. Deploy to Vercel

```bash
npm i -g vercel
vercel --prod
```

Add `GEMINI_KEY` and `JWT_SECRET` as environment variables in your Vercel dashboard.

## Project Structure

```
├── app.py               # Flask entry point & API routes
├── lib/
│   ├── agents.py        # Multi-agent pipeline (plan, generate, review, refactor)
│   ├── auth.py          # JWT authentication & decorators
│   ├── database.py      # SQLite / Supabase connections
│   └── llm.py           # Google Gemini integration
├── static/
│   ├── css/styles.css   # Stylesheet
│   └── js/app.js        # Client-side application
├── index.html           # Single-page frontend
├── vercel.json          # Vercel deployment config
├── requirements.txt     # Python dependencies
└── .env.example         # Environment variable template
```

## API Reference

### Authentication

| Method | Endpoint              | Description         |
| ------ | --------------------- | ------------------- |
| POST   | `/api/auth/register`  | Create account      |
| POST   | `/api/auth/login`     | Sign in             |
| GET    | `/api/auth/me`        | Current user info   |

### Projects

| Method | Endpoint                          | Description          |
| ------ | --------------------------------- | -------------------- |
| GET    | `/api/projects`                   | List projects        |
| POST   | `/api/projects`                   | Create project       |
| GET    | `/api/projects/:id`               | Project details      |
| GET    | `/api/projects/:id/export`        | Download ZIP         |

### Generation Pipeline

| Method | Endpoint               | Description                  |
| ------ | ---------------------- | ---------------------------- |
| POST   | `/api/refine-prompt`   | Refine user input            |
| POST   | `/api/generate-plan`   | Generate architecture plan   |
| POST   | `/api/generate-system` | Build, review & refactor     |

### Utility

| Method | Endpoint   | Description         |
| ------ | ---------- | ------------------- |
| GET    | `/health`  | Health check        |
| GET    | `/api`     | API information     |

## License

Educational project by John Rish Ladica for SLSU-HC — Society of Information Technology Students (SITS).

See [LICENSE](LICENSE) for details.

