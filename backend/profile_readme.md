# Hi 👋, I'm Atul Mishra

**AI Software Engineer & Data Science Student at IIT Madras**  
*Specializing in Autonomous LLM Agents (LangGraph), Deep Learning, and Scalable Web Architectures*

<div align="center">
  <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&pause=1000&color=00D9FF&center=true&vCenter=true&width=435&lines=Building+Intelligent+Systems;Web+Infrastructure+%2B+Generative+AI;Engineering+Autonomous+Agents" alt="Typing SVG" />
</div>

---

### 👨‍💻 About Me

*   🎓 **BS in Data Science & Applications** at **IIT Madras** (CGPA: 7.6 | 2023 -- 2027)
*   💼 **AI Engineering Intern** at **IIT Ropar (VLED Lab)** (May 2026 -- Present)
    *   *Engineering production LLM tooling (LangGraph, LangChain) for a live open-source educational platform undercse department faculty guidance.*
    *   *Developing full-stack MERN modules (React, Express, MongoDB) to integrate AI capabilities into real-world student products.*
*   🔭 **Research Interest**: Multi-agent orchestration, audio/multimodal deep learning, and database query optimization.
*   🏆 **Leadership**: Founded and organized the *Code Crafters Hackathon* at IIT Madras.

---

### 🌐 Connect With Me

<p align="left">
  <a href="https://linkedin.com/in/atulmishra2264" target="_blank">
    <img src="https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn"/>
  </a>
  <a href="https://github.com/Atulmishra22" target="_blank">
    <img src="https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"/>
  </a>
  <a href="mailto:atulmishralearn@gmail.com" target="_blank">
    <img src="https://img.shields.io/badge/Email-D14836?style=for-the-badge&logo=gmail&logoColor=white" alt="Email"/>
  </a>
  <a href="https://atul-mishra-portfolio.vercel.app" target="_blank">
    <img src="https://img.shields.io/badge/Portfolio-FF5722?style=for-the-badge&logo=google-chrome&logoColor=white" alt="Portfolio"/>
  </a>
</p>

---

### 🛠️ Tech Stack

| Category | Tools & Technologies |
| :--- | :--- |
| **Languages** | ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) ![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat&logo=javascript&logoColor=black) ![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=flat&logo=typescript&logoColor=white) ![SQL](https://img.shields.io/badge/SQL-4479A1?style=flat&logo=mysql&logoColor=white) |
| **AI / Deep Learning** | ![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?style=flat&logo=pytorch&logoColor=white) ![Lightning](https://img.shields.io/badge/Lightning-792EE5?style=flat&logo=pytorchlightning&logoColor=white) ![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat&logo=scikitlearn&logoColor=white) ![Pandas](https://img.shields.io/badge/Pandas-150458?style=flat&logo=pandas&logoColor=white) ![NumPy](https://img.shields.io/badge/NumPy-013243?style=flat&logo=numpy&logoColor=white) |
| **LLM Orchestration** | ![LangGraph](https://img.shields.io/badge/LangGraph-00D9FF?style=flat&logo=chainlink&logoColor=white) ![LangChain](https://img.shields.io/badge/LangChain-121212?style=flat&logo=chainlink&logoColor=white) ![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=flat&logo=openai&logoColor=white) ![LiteLLM](https://img.shields.io/badge/LiteLLM-4A154B?style=flat) |
| **Backend & Devops** | ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white) ![Flask](https://img.shields.io/badge/Flask-000000?style=flat&logo=flask&logoColor=white) ![Node.js](https://img.shields.io/badge/Node.js-339933?style=flat&logo=node.js&logoColor=white) ![Express](https://img.shields.io/badge/Express-000000?style=flat&logo=express&logoColor=white) ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) ![Docker](https://img.shields.io/badge/Celery-37814A?style=flat&logo=celery&logoColor=white) |
| **Frontend & DBs** | ![React](https://img.shields.io/badge/React-20232A?style=flat&logo=react&logoColor=61DAFB) ![Vue.js 3](https://img.shields.io/badge/Vue.js_3-35495E?style=flat&logo=vue.js&logoColor=4FC08D) ![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=flat&logo=mongodb&logoColor=white) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=flat&logo=postgresql&logoColor=white) ![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white) |

---

### 🚀 Featured Projects

#### 🤖 [AI Quiz Solver --- Autonomous Multi-Agent System](https://github.com/Atulmishra22/llm-quiz-solver)
*An intelligent agent framework built to solve multi-step data science challenges autonomously.*
*   **Architecture**: Designed a **dual AI agent** with LangGraph and LangChain, routing reasoning to a primary LLM (GPT-5-nano) and offloading multimodal work to a backup (Gemini 2.0 Flash) on API rate-limits.
*   **Engineering**: Integrated Playwright for rendering dynamic SPAs, built dynamic Python sandboxed execution, and established a sub-2-second rate-limiting retry mechanism to complete tasks under a **3-minute** time budget.
*   **Results**: Achieved **98% accuracy** on evaluation sets; containerized via Docker for deployment on HuggingFace Spaces.

#### 🎵 [Messy Mashup --- Music Genre Classification System](https://github.com/Atulmishra22/Messy-Mashup-Music-Genre-Classification)
*Deep learning audio classification system for highly noisy, stem-mixed music files.*
*   **Architecture**: Built a PyTorch ensemble combining a fine-tuned **Audio Spectrogram Transformer (AST)** (0.75 weight) and a scratch **CRNN (CNN + BiGRU + Soft Attention)** (0.25 weight).
*   **Engineering**: Implemented PyTorch gradient accumulation to fit the 86M-parameter AST model into restricted GPU memory. Handled data distribution gaps using same-genre stem mixing and dynamic audio tiling to eliminate zero-padding silence out-of-distribution bugs.
*   **Results**: Achieved a **0.917 Macro F1 score**, outperforming the competition target of 0.80 by **14.6%**. Deployed on HuggingFace with a Gradio UI.

#### 🧬 [Protein Secondary Structure Prediction](https://github.com/Atulmishra22/protein-secondary-structure-prediction)
*Sequence-to-sequence deep learning network predicting residue-level secondary structural elements.*
*   **Architecture**: Developed a **Compact Hybrid LSTM** using PyTorch Lightning, integrating a 1D CNN front-end (for local motifs like alpha-helices) with a Bi-LSTM layer and a 2-Head Self-Attention block (for global long-range beta-sheets).
*   **Engineering**: Tackled extreme class imbalance (Pi-helix < 0.1%) by formulating a custom weighted cross-entropy loss function and applying token masking augmentations to improve minority class recall.
*   **Results**: Reached a **0.478 overall validation score** (harmonic mean of Q8 and Q3 F1), representing a +0.016 improvement over traditional Bi-LSTM baselines.

#### 💼 [Full-Stack Campus Placement Portal](https://github.com/Atulmishra22/placement-portal)
*Multi-role recruitment portal managing student profiles, company openings, and interview pipelines.*
*   **Architecture**: Vue.js 3 SPA frontend (Pinia state management) and Flask REST API backend with a custom "Editorial Brutalism" dark-theme layout.
*   **Engineering**: Secured API endpoints with stateless JWT authentication and Role-Based Access Control (RBAC). Optimized query performance by leveraging Flask-SQLAlchemy **`joinedload()` eager loading** to eliminate N+1 database roundtrips. Integrated cascade deletions to maintain relational integrity.

---

### 📊 GitHub Statistics

<div align="center">
  <img src="https://github-readme-streak-stats.herokuapp.com/?user=atulmishra22&theme=tokyonight" alt="GitHub Streak" /><br><br>
  <img src="https://github-readme-activity-graph.vercel.app/graph?username=atulmishra22&theme=tokyo-night&hide_border=true" alt="Contribution Graph" />
</div>

---

### 🏆 Key Achievements
*   💻 **120+ LeetCode** problems solved (focused on algorithms and graphs).
*   🚀 **4+ Production AI/Web applications** deployed on Render and HuggingFace Spaces.
*   📈 **Active Kaggle Competitor** in computer vision and audio classification tracks.

---

<div align="center">
  <img src="https://komarev.com/ghpvc/?username=atulmishra22&label=Profile%20views&color=0e75b6&style=for-the-badge" alt="Profile views" />
  <br>
  <i>⚡ "Engineering Intelligent Systems" ⚡</i>
</div>
