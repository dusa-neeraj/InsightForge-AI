# InsightForge AI

**An AI-powered data analysis platform for faster, smarter insights.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Visit%20App-blue?style=for-the-badge)](https://insight-forge-ai-silk.vercel.app/)

InsightForge AI is a full-stack data analysis platform that helps users transform raw datasets into meaningful insights. It combines data cleaning, statistical profiling, exploratory data analysis, interactive visualizations, AI-powered explanations, natural-language data chat, and report generation in one application.

The goal is to make data analysis more accessible by allowing users to explore datasets, understand patterns, investigate questions, and communicate findings without relying entirely on manual analysis.

## Live Demo

**Try the application:** https://insight-forge-ai-silk.vercel.app/

The application is deployed with Vercel for the frontend and Render for the backend.

## Key Features

- **Dataset Upload:** Upload CSV and Excel datasets for analysis.
- **Data Cleaning:** Identify and handle common data-quality issues.
- **Data Profiling:** Inspect column types, missing values, descriptive statistics, and dataset structure.
- **Exploratory Data Analysis (EDA):** Explore distributions, trends, and relationships using visualizations.
- **Interactive Dashboards:** Visualize important patterns and analytical results.
- **Key Performance Indicators (KPIs):** Calculate useful metrics to support data-driven decisions.
- **AI-Powered Insights:** Generate natural-language explanations of analytical findings.
- **AI Data Chat:** Ask questions about datasets using natural language.
- **SQL Analysis:** Run supported, restricted SQL queries against data.
- **Data Quality Analysis:** Examine data-quality issues before using a dataset for further analysis.
- **Downloadable Reports:** Generate PDF reports containing analytical summaries and charts.
- **Export Support:** Download cleaned datasets and generated reports.
- **Automated Testing:** Test important backend functionality, validation rules, and error-handling scenarios.

## Technology Stack

| Area | Technologies |
|---|---|
| Frontend | React, Vite, Tailwind CSS |
| Data Visualization | Plotly |
| Backend API | Python, FastAPI |
| Data Processing | Pandas |
| Testing | Pytest |
| Deployment | Vercel, Render |

## Application Workflow

1. **Upload:** Import a CSV or Excel dataset.
2. **Profile:** Examine dataset structure, column types, and summary statistics.
3. **Clean:** Identify and address common data-quality problems.
4. **Analyze:** Explore patterns, distributions, relationships, and KPIs.
5. **Generate Insights:** Review AI-assisted explanations of analytical findings.
6. **Ask Questions:** Interact with the dataset using natural language and supported SQL queries.
7. **Export:** Download cleaned data and analytical reports.

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

## Getting Started Locally

### Prerequisites

Install the following before running the project:

- Python
- Node.js and npm
- Git

### 1. Clone the repository

```bash
git clone https://github.com/dusa-neeraj/InsightForge-AI.git
cd InsightForge-AI
```

### 2. Set up the backend

Create a Python virtual environment from the project root.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

If PowerShell blocks environment activation, you can run the virtual environment's Python executable directly instead.

Create your local backend environment configuration using `backend/.env.example` as a reference, if that file is present in your repository. Configure the required environment variables and API credentials locally.

**Never commit real API keys, passwords, or secrets to GitHub.**

Start the backend from the project root:

```bash
uvicorn main:app --reload --app-dir backend
```

The backend should be available at:

- API: http://localhost:8000
- Interactive API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### 3. Set up the frontend

Open a second terminal and run:

```bash
cd frontend
npm install
```

Create a `.env` file in the `frontend` directory:

```env
VITE_API_URL=http://localhost:8000
```

Start the frontend development server:

```bash
npm run dev
```

Open the local URL printed in the terminal, usually http://localhost:5173.

### 4. Run the tests

From the project root, execute the backend test suite using the virtual environment's Python interpreter:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

The latest recorded backend test run completed with **248 passing tests**. Run the suite again after code changes to verify the current state.

## Security and Data Handling

- Store credentials in environment variables or your deployment provider's environment settings.
- Never commit `.env` files containing real secrets.
- Validate uploaded files and use supported file formats.
- Keep private datasets and sensitive generated reports out of public repositories.
- Use only supported, restricted SQL operations.
- Review data-retention and deletion behavior before uploading sensitive information.
- Avoid uploading confidential or personally identifiable information to a public demo.

## Deployment

InsightForge AI is deployed using:

- **Frontend:** Vercel
- **Backend:** Render

The live frontend is available at:

https://insight-forge-ai-silk.vercel.app/

Deployment configuration and environment variables should be maintained in the respective hosting dashboards. Keep API credentials private and configure the backend's allowed frontend origins appropriately.

## Current Status

**Deployed and tested.**

InsightForge AI is a portfolio project demonstrating full-stack development, data analysis, API design, data visualization, AI-assisted workflows, automated testing, and cloud deployment.

## Future Improvements

Potential areas for further development include:

- Performance optimization for large datasets.
- More advanced analytical and visualization options.
- Expanded automated testing and deployment checks.
- Improved user experience for long-running analysis tasks.
- Additional export formats and analytical reporting capabilities.

## Author

**Neeraj Dusa**

GitHub: https://github.com/dusa-neeraj

---

If you find the project useful, consider giving the repository a star!
