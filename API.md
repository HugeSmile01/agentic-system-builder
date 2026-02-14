# API Documentation

## Base URL

- **Local**: `http://localhost:5000`
- **Production**: `https://your-domain.vercel.app`

## Authentication

All protected endpoints require a JWT token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

Tokens are obtained via `/api/auth/login` or `/api/auth/register` and are valid for 24 hours.

## Endpoints

### Authentication

#### POST /api/auth/register

Register a new user account.

**Rate Limit**: 5 per hour

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "full_name": "John Doe"
}
```

**Response** (200):
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe"
  }
}
```

**Errors**:
- `400`: Email/password required, invalid format, or password too short
- `409`: User already exists

---

#### POST /api/auth/login

Sign in to an existing account.

**Rate Limit**: 10 per hour

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response** (200):
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe"
  }
}
```

**Errors**:
- `400`: Email/password required
- `401`: Invalid credentials

---

#### GET /api/auth/me

Get current user information.

**Auth**: Required

**Response** (200):
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "created_at": "2026-02-14T06:00:00.000Z"
}
```

---

#### PUT /api/auth/update-profile

Update user profile information.

**Auth**: Required

**Request Body**:
```json
{
  "full_name": "Jane Doe"
}
```

**Response** (200):
```json
{
  "message": "Profile updated successfully",
  "full_name": "Jane Doe"
}
```

---

#### PUT /api/auth/change-password

Change user password.

**Auth**: Required

**Request Body**:
```json
{
  "current_password": "oldpassword",
  "new_password": "newpassword123"
}
```

**Response** (200):
```json
{
  "message": "Password changed successfully"
}
```

**Errors**:
- `400`: Passwords required or new password too short
- `401`: Current password incorrect

---

#### POST /api/auth/forgot-password

Request a password reset token.

**Rate Limit**: 3 per hour

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Response** (200):
```json
{
  "message": "If an account exists with this email, a reset link has been sent"
}
```

**Note**: Currently generates token but doesn't send email. Email integration needed for production.

---

#### POST /api/auth/reset-password

Reset password using a reset token.

**Rate Limit**: 5 per hour

**Request Body**:
```json
{
  "token": "reset-token-from-email",
  "new_password": "newsecurepassword123"
}
```

**Response** (200):
```json
{
  "message": "Password reset successfully"
}
```

**Errors**:
- `400`: Token/password required or password too short
- `401`: Invalid or expired token

---

### Projects

#### GET /api/projects

List all projects accessible to the current user (owned + collaborated).

**Auth**: Required

**Query Parameters**:
- `search` (optional): Search in name, description, or goal
- `status` (optional): Filter by status (`draft`, `generated`, `archived`)
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Results per page (default: 50, max: 100)

**Response** (200):
```json
{
  "projects": [
    {
      "id": 1,
      "user_id": 1,
      "name": "My Project",
      "description": "A great project",
      "goal": "Build something awesome",
      "audience": "Developers",
      "ui_style": "Modern",
      "constraints": "Free tier only",
      "status": "draft",
      "created_at": "2026-02-14T06:00:00.000Z",
      "updated_at": "2026-02-14T06:00:00.000Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 10,
    "pages": 1
  }
}
```

---

#### POST /api/projects

Create a new project.

**Auth**: Required  
**Rate Limit**: 10 per hour

**Request Body**:
```json
{
  "name": "My New Project",
  "goal": "Build a task management system",
  "description": "For small teams",
  "audience": "Freelancers",
  "ui_style": "Minimal",
  "constraints": "Deploy to Vercel"
}
```

**Response** (200):
```json
{
  "id": 2,
  "name": "My New Project",
  "status": "draft"
}
```

**Errors**:
- `400`: Name and goal are required

---

#### GET /api/projects/:id

Get detailed information about a specific project.

**Auth**: Required  
**Access**: Owner or collaborator

**Response** (200):
```json
{
  "project": {
    "id": 1,
    "name": "My Project",
    "goal": "...",
    "status": "generated"
  },
  "iterations": [
    {
      "id": 1,
      "iteration_number": 1,
      "refined_prompt": {...},
      "plan": {...},
      "review_notes": {...}
    }
  ],
  "files": [
    {
      "id": 1,
      "filename": "app.py",
      "content": "...",
      "file_type": "py"
    }
  ],
  "access": {
    "role": "owner",
    "is_owner": true
  }
}
```

**Errors**:
- `404`: Project not found or no access

---

#### PUT /api/projects/:id

Update project details.

**Auth**: Required  
**Access**: Owner or editor

**Request Body**:
```json
{
  "name": "Updated Project Name",
  "description": "Updated description"
}
```

**Response** (200):
```json
{
  "message": "Project updated successfully",
  "id": 1
}
```

**Errors**:
- `400`: Name is required
- `403`: Insufficient permissions (viewer role)
- `404`: Project not found

---

#### DELETE /api/projects/:id

Delete a project and all associated data.

**Auth**: Required  
**Access**: Owner only

**Response** (200):
```json
{
  "message": "Project deleted successfully"
}
```

**Errors**:
- `404`: Project not found or insufficient permissions

---

#### GET /api/projects/:id/export

Export project as a ZIP file.

**Auth**: Required  
**Rate Limit**: 10 per hour  
**Access**: Owner or collaborator

**Response** (200): Binary ZIP file

**Errors**:
- `404`: Project not found, no access, or no files to export

---

### Collaborators

#### GET /api/projects/:id/collaborators

List all collaborators for a project.

**Auth**: Required  
**Access**: Owner

**Response** (200):
```json
{
  "collaborators": [
    {
      "id": 1,
      "user_id": 2,
      "role": "editor",
      "added_at": "2026-02-14T06:00:00.000Z",
      "email": "collaborator@example.com",
      "full_name": "Jane Smith"
    }
  ]
}
```

---

#### POST /api/projects/:id/collaborators

Add a collaborator to a project.

**Auth**: Required  
**Access**: Owner only

**Request Body**:
```json
{
  "email": "collaborator@example.com",
  "role": "editor"
}
```

**Valid roles**: `viewer`, `editor`

**Response** (200):
```json
{
  "message": "Collaborator added successfully",
  "user_id": 2,
  "email": "collaborator@example.com",
  "role": "editor"
}
```

**Errors**:
- `400`: Email required, invalid format, or invalid role
- `404`: Project or user not found
- `409`: User is already a collaborator

---

#### DELETE /api/projects/:id/collaborators/:user_id

Remove a collaborator from a project.

**Auth**: Required  
**Access**: Owner only

**Response** (200):
```json
{
  "message": "Collaborator removed successfully"
}
```

**Errors**:
- `404`: Project or collaborator not found

---

### Generation Pipeline

#### POST /api/refine-prompt

Refine user input into a detailed specification (Step 1).

**Auth**: Required  
**Rate Limit**: 20 per hour

**Request Body**:
```json
{
  "prompt": "I want to build a task manager",
  "project_id": 1,
  "context": "Additional context about the project"
}
```

**Response** (200):
```json
{
  "refined": {
    "goal": "...",
    "audience": "...",
    "features": [...],
    "technical_requirements": {...},
    "ui_requirements": {...}
  },
  "original": "I want to build a task manager"
}
```

**Errors**:
- `400`: Prompt required or exceeds maximum length
- `500`: AI service failure

---

#### POST /api/generate-plan

Generate an implementation plan (Step 2).

**Auth**: Required  
**Rate Limit**: 15 per hour

**Request Body**:
```json
{
  "refined_spec": {...},
  "project_id": 1
}
```

**Response** (200):
```json
{
  "plan": {
    "architecture": "...",
    "file_structure": [...],
    "implementation_steps": [...],
    "technology_stack": {...}
  }
}
```

**Errors**:
- `400`: Refined specification required
- `500`: AI service failure

---

#### POST /api/generate-system

Generate, review, and refactor complete system (Step 3).

**Auth**: Required  
**Rate Limit**: 5 per hour

**Request Body**:
```json
{
  "plan": {...},
  "refined_spec": {...},
  "project_id": 1
}
```

**Response** (200):
```json
{
  "files": {
    "app.py": 12543,
    "index.html": 8234,
    "requirements.txt": 156
  },
  "review": {
    "overall_score": 85,
    "security_issues": [],
    "quality_issues": [],
    "deployment_ready": true
  },
  "refactor_message": "Refactored 2 files",
  "total_files": 5
}
```

**Errors**:
- `400`: Plan and refined specification required
- `500`: AI service failure or generation timeout

---

### Utility

#### GET /health

Health check endpoint.

**Response** (200):
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

**Response** (503): When unhealthy
```json
{
  "status": "degraded",
  "database": "error",
  "database_error": "Connection failed"
}
```

---

#### GET /api

API information and available endpoints.

**Response** (200):
```json
{
  "service": "Agentic System Builder API",
  "version": "3.1.1",
  "author": "John Rish Ladica – SLSU-HC SITS",
  "endpoints": {...},
  "features": [...]
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": "Error message",
  "timestamp": "2026-02-14T06:00:00.000Z"
}
```

### Common HTTP Status Codes

- `200`: Success
- `400`: Bad Request (validation error)
- `401`: Unauthorized (invalid/missing token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found
- `409`: Conflict (duplicate resource)
- `429`: Too Many Requests (rate limit exceeded)
- `500`: Internal Server Error

---

## Rate Limiting

Rate limits are applied per IP address. When exceeded, the API returns:

```json
{
  "error": "Too many requests",
  "timestamp": "2026-02-14T06:00:00.000Z"
}
```

**Default Limits**:
- Global: 200 requests per hour
- Registration: 5 per hour
- Login: 10 per hour
- Project creation: 10 per hour
- System generation: 5 per hour

---

## Best Practices

1. **Authentication**: Store JWT tokens securely (httpOnly cookies recommended)
2. **Error Handling**: Always check response status codes
3. **Rate Limits**: Implement exponential backoff when hitting rate limits
4. **Input Validation**: Validate data client-side before sending
5. **File Size**: Keep generated files under 1MB each
6. **Pagination**: Use pagination for large result sets

---

**Last Updated**: February 2026  
**API Version**: 3.1.1  
**Author**: John Rish Ladica, Student Leader at SLSU-HC – Society of Information Technology Students (SITS)
