"""Tests for the LaTeX resume parser."""
from __future__ import annotations

import pytest

from app.utils.latex import parse_latex_resume

SAMPLE_RESUME = r"""
\documentclass{article}
\usepackage{hyperref}
\author{Jane Doe}
\begin{document}
\name{Jane}{Doe}
jane.doe@example.com | github.com/janedoe | linkedin.com/in/janedoe

\section{Experience}
\cventry{Jun 2022 -- Present}{Software Engineer}{Acme Corp}{San Francisco, CA}{}{
\begin{itemize}
  \item Built a distributed caching layer using Redis, reducing p99 latency by 40\%
  \item Led migration from monolith to microservices serving 10M daily active users
\end{itemize}
}

\section{Education}
\cventry{2018 -- 2022}{B.S. Computer Science}{MIT}{Cambridge, MA}{}{}

\section{Skills}
Python, TypeScript, Go, PostgreSQL, Redis, Docker, Kubernetes

\end{document}
"""


def test_parse_name():
    result = parse_latex_resume(SAMPLE_RESUME)
    assert "Jane" in result.name or "Doe" in result.name


def test_parse_email():
    result = parse_latex_resume(SAMPLE_RESUME)
    assert result.email == "jane.doe@example.com"


def test_parse_github():
    result = parse_latex_resume(SAMPLE_RESUME)
    assert "janedoe" in result.github


def test_parse_linkedin():
    result = parse_latex_resume(SAMPLE_RESUME)
    assert "janedoe" in result.linkedin


def test_parse_experience():
    result = parse_latex_resume(SAMPLE_RESUME)
    assert len(result.experience) >= 1
    exp = result.experience[0]
    assert len(exp.bullets) >= 1
    assert any("Redis" in b.text or "latency" in b.text for b in exp.bullets)


def test_parse_skills():
    result = parse_latex_resume(SAMPLE_RESUME)
    assert len(result.skills) >= 3
    skills_text = " ".join(result.skills).lower()
    assert "python" in skills_text or "typescript" in skills_text


def test_to_dict_shape():
    result = parse_latex_resume(SAMPLE_RESUME)
    d = result.to_dict()
    assert "experience" in d
    assert "education" in d
    assert "skills" in d
    assert "projects" in d
    assert isinstance(d["experience"], list)


def test_empty_source():
    result = parse_latex_resume("")
    assert result.name == ""
    assert result.email == ""
