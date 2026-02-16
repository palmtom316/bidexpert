import unittest
from unittest.mock import MagicMock
import uuid
from datetime import datetime
from app.services.scoring_engine import SimulatedScorer
from app.models.tables import Requirement, ReviewReport, SectionContent, ScoringReport

class TestSimulatedScorer(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.scorer = SimulatedScorer(self.mock_db)
        self.project_id = str(uuid.uuid4())

    def test_calculate_score_full_pass(self):
        # 1. Requirements
        req1 = MagicMock(spec=Requirement)
        req1.requirement_code = "REQ-1"
        req1.score_weight = 10.0
        req1.project_id = uuid.UUID(self.project_id)
        
        req2 = MagicMock(spec=Requirement)
        req2.requirement_code = "REQ-2"
        req2.score_weight = 5.0
        req2.project_id = uuid.UUID(self.project_id)
        
        self.mock_db.scalars.return_value.all.side_effect = [
            [req1, req2], # Requirements
            [ # Sections
                MagicMock(spec=SectionContent, requirement_codes=["REQ-1"], section_key="1.1", project_id=uuid.UUID(self.project_id)),
                MagicMock(spec=SectionContent, requirement_codes=["REQ-2"], section_key="1.2", project_id=uuid.UUID(self.project_id))
            ],
            [ # Reports
                MagicMock(spec=ReviewReport, section_key="1.1", status="PASS", report_json={}, created_at=datetime.now(), project_id=self.project_id),
                MagicMock(spec=ReviewReport, section_key="1.2", status="PASS", report_json={}, created_at=datetime.now(), project_id=self.project_id)
            ]
        ]
        
        report = self.scorer.calculate_score(self.project_id)
        
        self.assertEqual(report.score_total, 15.0)
        self.assertEqual(len(report.details_json["items"]), 2)
        self.mock_db.add.assert_called_once()

    def test_calculate_score_partial_fail(self):
        # REQ-1 Pass, REQ-2 Fail
        req1 = MagicMock(spec=Requirement)
        req1.requirement_code = "REQ-1"
        req1.score_weight = 10.0
        
        req2 = MagicMock(spec=Requirement)
        req2.requirement_code = "REQ-2"
        req2.score_weight = 5.0
        
        self.mock_db.scalars.return_value.all.side_effect = [
            [req1, req2],
            [
                MagicMock(spec=SectionContent, requirement_codes=["REQ-1"], section_key="1.1"),
                MagicMock(spec=SectionContent, requirement_codes=["REQ-2"], section_key="1.2")
            ],
            [
                MagicMock(spec=ReviewReport, section_key="1.1", status="PASS", report_json={}, created_at=datetime.now()),
                MagicMock(spec=ReviewReport, section_key="1.2", status="FAIL", report_json={"modeled_issues": [{"requirement_code": "REQ-2", "description": "Failure"}]}, created_at=datetime.now())
            ]
        ]
        
        report = self.scorer.calculate_score(self.project_id)
        
        self.assertEqual(report.score_total, 10.0)
        items = report.details_json["items"]
        self.assertEqual(items[0]["status"], "PASS")
        self.assertEqual(items[1]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
