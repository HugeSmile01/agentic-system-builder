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
- **Password Reset** — Token-based password recovery system
- **Profile Management** — Update user profile and change password
- **Project Collaboration** — Share projects with team members (viewer/editor roles)
- **Search & Filter** — Find projects quickly with search and status filters
- **Pagination** — Efficient handling of large project lists
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

### 4. Deploy to Production

See [DEPLOYMENT.md](DEPLOYMENT.md) for comprehensive deployment instructions covering:
- Vercel (recommended)
- Railway
- Docker
- Security checklist
- Database setup with Supabase
- Environment configuration
- Monitoring and troubleshooting

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

See [API.md](API.md) for complete API documentation including:
- Authentication endpoints (register, login, password reset)
- Project management (CRUD operations)
- Collaboration features (add/remove collaborators)
- Generation pipeline (refine, plan, generate)
- Rate limits and error handling
- Request/response examples

Quick reference:

### Authentication

| Method | Endpoint                     | Description              |
| ------ | ---------------------------- | ------------------------ |
| POST   | `/api/auth/register`         | Create account           |
| POST   | `/api/auth/login`            | Sign in                  |
| GET    | `/api/auth/me`               | Current user info        |
| PUT    | `/api/auth/update-profile`   | Update profile           |
| PUT    | `/api/auth/change-password`  | Change password          |
| POST   | `/api/auth/forgot-password`  | Request password reset   |
| POST   | `/api/auth/reset-password`   | Reset password with token|

### Projects

| Method | Endpoint                                 | Description              |
| ------ | ---------------------------------------- | ------------------------ |
| GET    | `/api/projects`                          | List projects (with search, filter, pagination) |
| POST   | `/api/projects`                          | Create project           |
| GET    | `/api/projects/:id`                      | Project details          |
| PUT    | `/api/projects/:id`                      | Update project           |
| DELETE | `/api/projects/:id`                      | Delete project           |
| GET    | `/api/projects/:id/export`               | Download ZIP             |
| GET    | `/api/projects/:id/collaborators`        | List collaborators       |
| POST   | `/api/projects/:id/collaborators`        | Add collaborator         |
| DELETE | `/api/projects/:id/collaborators/:user_id` | Remove collaborator   |

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

