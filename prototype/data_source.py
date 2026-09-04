"""Data source layer.

`DigestDataSource` is the interface the rest of the pipeline depends on.
`MockJiraDataSource` is a stand-in for a real Jira client: it reads the same
shape of data (projects / SLA metrics / issues) from local JSON fixtures
instead of calling the Jira REST API. Swapping in a real client later means
writing one more class with the same three methods -- nothing else in the
pipeline needs to change.
"""

import json
from abc import ABC, abstractmethod
from datetime import date, timedelta
from pathlib import Path
from typing import List

from .models import Issue, Project, SLA

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class DigestDataSource(ABC):
    @abstractmethod
    def fetch_projects(self) -> List[Project]: ...

    @abstractmethod
    def fetch_slas(self) -> List[SLA]: ...

    @abstractmethod
    def fetch_issues(self) -> List[Issue]: ...


class MockJiraDataSource(DigestDataSource):
    """Reads mock project/SLA/issue data from data/*.json, relative to today."""

    def __init__(self, data_dir: Path = DATA_DIR, today: date = None):
        self.data_dir = data_dir
        self.today = today or date.today()

    def _load(self, filename: str) -> list:
        with open(self.data_dir / filename, encoding="utf-8") as f:
            return json.load(f)

    def fetch_projects(self) -> List[Project]:
        rows = self._load("projects.json")
        return [
            Project(
                key=row["key"],
                name=row["name"],
                owner=row["owner"],
                reported_status=row["reported_status"],
                start_date=self.today - timedelta(days=row["start_days_ago"]),
                planned_end_date=self.today + timedelta(days=row["planned_end_days_from_now"]),
                completion_pct=row["completion_pct"],
            )
            for row in rows
        ]

    def fetch_slas(self) -> List[SLA]:
        rows = self._load("slas.json")
        return [
            SLA(
                name=row["name"],
                owner=row["owner"],
                unit=row["unit"],
                current_value=row["current_value"],
                target=row["target"],
                direction=row["direction"],
            )
            for row in rows
        ]

    def fetch_issues(self) -> List[Issue]:
        rows = self._load("issues.json")
        return [
            Issue(
                key=row["key"],
                title=row["title"],
                project_key=row["project_key"],
                priority=row["priority"],
                assignee=row["assignee"],
                created_date=self.today - timedelta(days=row["created_days_ago"]),
                is_blocking=row["is_blocking"],
                is_overdue=row["is_overdue"],
            )
            for row in rows
        ]
