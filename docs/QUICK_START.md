# Venue Management System - Quick Start Guide

## Prerequisites
- Python 3.9+
- Node.js 16+
- PostgreSQL 12+
- Git

---

## 1. DATABASE SETUP

### Step 1: Create Database
```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE venue_system;
CREATE USER venue_user WITH PASSWORD 'your_secure_password';
ALTER ROLE venue_user SET client_encoding TO 'utf8';
ALTER ROLE venue_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE venue_user SET default_transaction_deferrable TO on;
ALTER ROLE venue_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE venue_system TO venue_user;
\q
```

### Step 2: Run Schema
```bash
# Run the SQL schema
psql -U venue_user -d venue_system -f database_schema.sql
```

---

## 2. BACKEND SETUP (Python/Flask)

### Step 1: Create Project Directory
```bash
mkdir venue-system-backend
cd venue-system-backend
```

### Step 2: Create Virtual Environment
```bash
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r flask_requirements.txt
```

### Step 4: Create Project Structure
```bash
mkdir app
mkdir app/models
mkdir app/routes
mkdir app/services
mkdir app/middleware
mkdir app/utils
touch app/__init__.py
touch run.py
```

### Step 5: Create .env File
```bash
cat > .env << EOF
FLASK_APP=run.py
FLASK_ENV=development
DEBUG=True

# Database
DATABASE_URL=postgresql://venue_user:your_secure_password@localhost:5432/venue_system

# JWT
JWT_SECRET_KEY=your_super_secret_key_change_this_in_production
JWT_ACCESS_TOKEN_EXPIRES=86400

# CORS
FLASK_CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Server
SERVER_PORT=5000
SERVER_HOST=0.0.0.0
EOF
```

### Step 6: Create Flask App Structure
```bash
# Create app/__init__.py with basic setup
# Create app/config.py with database configuration
# Create run.py as entry point
```

### Step 7: Test Backend
```bash
python run.py
# Should show: Running on http://127.0.0.1:5000
```

---

## 3. FRONTEND SETUP (Vue.js)

### Step 1: Create Vue Project
```bash
npm create vite@latest venue-system-frontend -- --template vue
cd venue-system-frontend
```

### Step 2: Install Dependencies
```bash
npm install
```

### Step 3: Add TailwindCSS
```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

### Step 4: Configure Tailwind
Edit `tailwind.config.js`:
```js
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

### Step 5: Create .env File
```bash
cat > .env << EOF
VITE_API_URL=http://localhost:5000/api
VITE_APP_NAME=Venue Management System
EOF
```

### Step 6: Test Frontend
```bash
npm run dev
# Should show: Local: http://localhost:5173
```

---

## 4. DEVELOPMENT WORKFLOW

### Terminal 1: Backend
```bash
cd venue-system-backend
source venv/bin/activate
python run.py
```

### Terminal 2: Frontend
```bash
cd venue-system-frontend
npm run dev
```

### Access Application
```
Frontend: http://localhost:5173
Backend API: http://localhost:5000/api
```

---

## 5. BASIC FLASK APP SKELETON

Create `app/__init__.py`:
```python
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import JWTManager
import os
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    
    # Config
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
    
    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    CORS(app, origins=os.getenv('FLASK_CORS_ORIGINS', 'http://localhost:3000').split(','))
    
    # Register blueprints
    # from app.routes import auth_bp, dashboard_bp, sales_bp, etc.
    # app.register_blueprint(auth_bp, url_prefix='/api/auth')
    # app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
    # etc...
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    return app
```

Create `run.py`:
```python
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('SERVER_PORT', 5000))
    app.run(host=os.getenv('SERVER_HOST', '0.0.0.0'), port=port, debug=True)
```

---

## 6. FIRST API ENDPOINT (Authentication)

Create `app/routes/auth.py`:
```python
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from werkzeug.security import check_password_hash, generate_password_hash
from app import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Missing credentials'}), 400
    
    user = User.query.filter_by(username=username).first()
    
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    access_token = create_access_token(identity=user.id)
    return jsonify({
        'access_token': access_token,
        'user': {
            'id': user.id,
            'username': user.username,
            'role': user.role
        }
    }), 200
```

---

## 7. FIRST VUE COMPONENT

Create `src/components/LoginForm.vue`:
```vue
<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="max-w-md w-full space-y-8">
      <h2 class="text-3xl font-bold text-center">Venue Management System</h2>
      
      <form @submit.prevent="login" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700">Username</label>
          <input 
            v-model="form.username" 
            type="text" 
            class="w-full px-3 py-2 border border-gray-300 rounded-md"
            required
          >
        </div>
        
        <div>
          <label class="block text-sm font-medium text-gray-700">Password</label>
          <input 
            v-model="form.password" 
            type="password" 
            class="w-full px-3 py-2 border border-gray-300 rounded-md"
            required
          >
        </div>
        
        <button 
          type="submit"
          class="w-full bg-blue-600 text-white py-2 rounded-md hover:bg-blue-700"
        >
          Login
        </button>
      </form>
      
      <div v-if="error" class="text-red-600 text-center">{{ error }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const form = ref({ username: '', password: '' })
const error = ref('')

const login = async () => {
  try {
    const response = await axios.post('/api/auth/login', form.value)
    localStorage.setItem('token', response.data.access_token)
    router.push('/dashboard')
  } catch (err) {
    error.value = err.response?.data?.error || 'Login failed'
  }
}
</script>
```

---

## 8. PROJECT CHECKLIST

### Phase 1: Foundation
- [ ] Database setup & verified
- [ ] Backend Flask app running
- [ ] Frontend Vue app running
- [ ] Authentication endpoint working
- [ ] Login component functional

### Phase 2: Sales Module
- [ ] Booking model & CRUD created
- [ ] Booking API endpoints working
- [ ] BookingForm component built
- [ ] BookingList component with filters
- [ ] Payment tracking implemented

### Phase 3: Operational Module
- [ ] Request model & CRUD
- [ ] Approval workflow implemented
- [ ] RequestForm component
- [ ] Budget tracking working

### Phase 4: Payroll Module
- [ ] Employee management CRUD
- [ ] Payroll calculation logic
- [ ] Payroll components built
- [ ] Approval workflow

### Phase 5: Procurement & Inventory
- [ ] PO creation & tracking
- [ ] Inventory management
- [ ] Stock transaction tracking
- [ ] Reorder alerts

### Phase 6: Financial Reports
- [ ] Report generation
- [ ] Analytics & charts
- [ ] Export functionality
- [ ] KPI dashboards

### Phase 7: Production Ready
- [ ] Testing complete
- [ ] Documentation done
- [ ] Security audit passed
- [ ] Performance optimized
- [ ] Deployed to production

---

## 9. COMMON COMMANDS

### Backend
```bash
# Run development server
python run.py

# Create database migrations
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# Run tests
pytest

# Format code
black app/
```

### Frontend
```bash
# Development
npm run dev

# Build for production
npm run build

# Preview build
npm run preview

# Lint & format
npm run lint
npm run format
```

---

## 10. TROUBLESHOOTING

### Database Connection Error
```bash
# Check PostgreSQL is running
psql -U postgres -d venue_system -c "SELECT version();"

# Verify database URL in .env
DATABASE_URL=postgresql://venue_user:password@localhost:5432/venue_system
```

### Port Already in Use
```bash
# Backend (change in .env or code)
# Frontend (Vite will try next port)
# Or kill process:
lsof -i :5000  # macOS/Linux
netstat -ano | findstr :5000  # Windows
```

### CORS Error
```bash
# Make sure FLASK_CORS_ORIGINS in .env matches frontend URL
FLASK_CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### Module Import Error
```bash
# Ensure you're in virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

---

## 11. NEXT STEPS

1. ✅ Complete this quick start
2. ⏳ Build authentication fully
3. ⏳ Implement sales module
4. ⏳ Add operational module
5. ⏳ Build payroll system
6. ⏳ Add procurement & inventory
7. ⏳ Create financial reports
8. ⏳ Test & deploy

**Let's build something great!** 🚀
