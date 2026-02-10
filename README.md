# Agentic System Builder v2.0

**Author**: John Rish Ladica  
**Affiliation**: SLSU-HC Student

A production-ready, autonomous AI system that generates complete, functional software systems through an intelligent multi-agent workflow.

## 🚀 Features

### Core Capabilities
- **Autonomous Planning**: AI-powered prompt refinement and specification generation
- **Multi-Agent Architecture**: Planner → Executor → Reviewer → Refactorer workflow
- **Complete Code Generation**: Generates full-stack applications with backend, frontend, and deployment configs
- **Quality Assurance**: Automated code review and refactoring
- **Project Management**: Full project lifecycle management with version tracking
- **Export System**: Download generated systems as ready-to-deploy ZIP archives

### Security & Authentication
- **JWT Authentication**: Secure token-based authentication system
- **Password Hashing**: Industry-standard password security
- **Rate Limiting**: Comprehensive API rate limiting
- **Input Validation**: Server-side validation for all inputs
- **CORS Protection**: Properly configured CORS for API security

### User Experience
- **iPhone-Optimized UI**: Mobile-first responsive design with safe area support
- **Dark Theme**: Beautiful dark interface with custom typography
- **Real-time Progress**: Live progress tracking for long-running operations
- **Auto-save**: Automatic draft saving to prevent data loss
- **Toast Notifications**: Contextual feedback for all user actions

## 📋 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Create `.env` file:
```env
GEMINI_KEY=your_gemini_api_key_here
JWT_SECRET=your_super_secret_jwt_key_min_32_chars_long
```

### 3. Run Locally
```bash
python app.py
```

Visit http://localhost:5000

### 4. Deploy to Vercel
```bash
vercel --prod
```

## 🏗️ System Architecture

### Multi-Agent Workflow
```
User Input → PLANNER → EXECUTOR → REVIEWER → REFACTORER → Final System
```

1. **Planner**: Refines user input into detailed specifications
2. **Executor**: Generates complete code files
3. **Reviewer**: Analyzes code for quality and security
4. **Refactorer**: Applies improvements based on review

## 📱 Usage

1. **Create Account**: Register with email and password
2. **New Project**: Describe what you want to build
3. **AI Refines**: System creates detailed specifications
4. **Generate**: Complete system generation with review
5. **Download**: Export as ready-to-deploy ZIP

## 🔐 Security Features

- JWT Authentication with secure tokens
- Password hashing with Werkzeug
- Rate limiting on all endpoints
- Input validation and sanitization
- SQL injection prevention
- CORS configuration

## 📊 API Endpoints

### Authentication
- `POST /api/auth/register` - Create account
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Get current user

### Projects
- `GET /api/projects` - List projects
- `POST /api/projects` - Create project
- `GET /api/projects/:id/export` - Download ZIP

### Agentic System
- `POST /api/refine-prompt` - Refine user input
- `POST /api/generate-plan` - Generate plan
- `POST /api/generate-system` - Generate complete system

## 🎯 Technology Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML5/CSS3/JavaScript
- **AI**: Google Gemini 1.5 Flash
- **Database**: SQLite / Supabase
- **Auth**: JWT tokens
- **Deployment**: Vercel

## 💡 Tips for Best Results

Write detailed prompts that include:
- Specific features and requirements
- Target users and their needs
- Technical constraints
- Success criteria

## 📄 License

Educational project by John Rish Ladica for SLSU-HC.

---

**Built with ❤️ using Google Gemini AI**
