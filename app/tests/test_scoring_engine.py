import unittest
from unittest.mock import MagicMock
import uuid
from datetime import datetime
from app.services.scoring_engine import SimulatedScorer, _estimate_requirement_coverage
from app.models.tables import Requirement, ReviewReport, SectionContent

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
        req1.original_text = "必须提供业绩证明"
        
        req2 = MagicMock(spec=Requirement)
        req2.requirement_code = "REQ-2"
        req2.score_weight = 5.0
        req2.original_text = "必须提供资质证明"
        
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

    def test_calculate_score_estimates_when_no_review_report(self):
        req = MagicMock(spec=Requirement)
        req.requirement_code = "REQ-1"
        req.score_weight = 10.0
        req.original_text = "必须提供资质证明"

        self.mock_db.scalars.return_value.all.side_effect = [
            [req],
            [
                MagicMock(
                    spec=SectionContent,
                    requirement_codes=["REQ-1"],
                    section_key="1.1",
                    content_md="我方将提交完整资质证明材料和扫描件。",
                )
            ],
            [],
        ]

        report = self.scorer.calculate_score(self.project_id)
        item = report.details_json["items"][0]

        self.assertGreater(report.score_total, 0.0)
        self.assertEqual(item["status"], "ESTIMATED_PASS")

    def test_estimate_coverage_does_not_pass_unrelated_long_text(self):
        supported, confidence = _estimate_requirement_coverage(
            "必须提交火星地幔样本报告",
            "本项目围绕绿色施工管理体系建设与组织协同机制进行说明。" * 20,
        )
        self.assertFalse(supported)
        self.assertEqual(confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
