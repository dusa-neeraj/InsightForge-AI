# InsightForge AI

**An AI-powered data analysis platform for faster, smarter insights.**

InsightForge AI is a full-stack data analysis application that helps users upload datasets, clean and explore data, visualize patterns, ask questions in natural language, and generate PDF reports.

## Features

- **Dataset Upload:** Upload CSV and Excel files for analysis.
- **Data Cleaning:** Identify and handle common data-quality issues.
- **Data Profiling:** Explore dataset structure, column types, missing values, and summary statistics.
- **Exploratory Data Analysis (EDA):** Analyze trends, distributions, and relationships with visualizations.
- **Key Performance Indicators:** Calculate useful metrics from your data.
- **AI-Powered Insights:** Generate natural-language explanations of analytical findings.
- **AI Data Chat:** Ask questions about your dataset using natural language.
- **SQL Analysis:** Run supported, restricted SQL queries against data.
- **PDF Reports:** Generate downloadable reports with charts and analytical summaries.
- **Backend Testing:** Includes automated tests for important API features and edge cases.

## Technology Stack

**Frontend**
- React
- Vite
- Tailwind CSS
- Plotly

**Backend**
- Python
- FastAPI
- Pandas
- Pytest

## Project Structure

```text
InsightForge-AI/
├── backend/
│   ├── agents/
│   ├── routes/
│   ├── services/
│   ├── tests/
│   ├── utils/
│   ├── config.py
│   ├── main.py
│   └── requirements.txt
├── frontend/
├── .gitignore
└── README.md
```

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/dusa-neeraj/InsightForge-AI.git
cd InsightForge-AI
```

### 2. Configure the backend

Create and activate a Python virtual environment, then install the backend dependencies.

```bash
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
pip install -r backend/requirements.txt
```

Create your local environment configuration using `backend/.env.example` as a reference. Add your own credentials where required. **Never commit real API keys or secrets.**

Start the backend from the project root:

```bash
uvicorn main:app --reload --app-dir backend
```

The API should be available at `http://localhost:8000`. Interactive API documentation is available at `http://localhost:8000/docs`.

### 3. Configure the frontend

Open a separate terminal:

```bash
cd frontend
npm install
```

Create a local frontend `.env` file with the backend URL:

```text
VITE_API_URL=http://localhost:8000
```

Start the frontend:

```bash
npm run dev
```

Open the local URL printed by Vite, usually `http://localhost:5173`.

## Running Tests

From the project root, run:

```bash
.venv\Scripts\python.exe -m pytest backend/tests -q
```

## Security

- Keep API keys and credentials in local environment files or your deployment provider's environment settings.
- Do not upload private datasets, generated reports, or virtual environments.
- Review all files before making the repository public.

## Deployment

The planned deployment uses **Render** for the FastAPI backend and **Vercel** for the React frontend. Live deployment links will be added here after deployment is complete.

## Project Status

Actively developed as a full-stack AI data analysis portfolio project.
